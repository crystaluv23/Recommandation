"""Compare input-only v6 and v12 matrices on exact frozen v182 identities."""
from __future__ import annotations

import argparse
from contextlib import contextmanager
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
from time import monotonic
from types import SimpleNamespace
from unittest.mock import patch

import diagnose_reviewed_periodic_operating_snapshot as periodic
from stock_opportunity_agent.artifacts import atomic_write_json, canonical_json_hash
from stock_opportunity_agent.cases.label_store import LabelStore
from stock_opportunity_agent.data.resolution import DataAcquisitionPolicy
from stock_opportunity_agent.data.reviewed_snapshot import ReviewedSourceRejected, open_raw_info_store
from stock_opportunity_agent.research.basic_info_orientation import compile_basic_info_requests
from stock_opportunity_agent.research.evolution_control import _build_evidence_resolver
from stock_opportunity_agent.research.evolution_core import default_information_plan, project_basic_info_bundle
from stock_opportunity_agent.signal_library import SignalRegistry, SignalExecutor


REPO = Path(__file__).resolve().parents[1]
ORIGIN = REPO / "runs/cold_start/minimal_rounds_v182_integrated/input_manifest.json"
ORIGIN_SHA = "3c6a74fea9c3e29742d9759f11a9087cbb16726e17d509ec1f4dd7d5e2b48d3c"
APPROVED_ROOT = REPO / "runs/cold_start/evolution/full-market-expanded-2025plus-v13-approved-inputs/expanded_dataset_proposal"
APPROVED = APPROVED_ROOT / "dataset_manifest.approved.json"
APPROVED_SHA = "13772d031162179f7468cb0e9d9aea0424f78084d18c65fe059d5b72840013e9"
ACQUISITION = APPROVED_ROOT / "acquisition_scope.json"
ACQUISITION_SHA = "5339d54fc73de68f227ac7d9e87d15adb60dc52454a758a8a8b3be55d33b3396"
PERIODIC_STAGE = periodic.DEFAULT_OUTPUT
HISTORY_REGISTRY = REPO / "runs/cold_start/evolution/information-evolution-jev-dual-self-evolution-20260928-v143/signals"
DEFAULT_OUTPUT = REPO / "runs/diagnostics/reviewed_frozen_case_inputs_20261020_v1/stage"
OWNING_SPEC = REPO / "spec/scripts/diagnose_reviewed_frozen_case_inputs.md"
COUNTS = {"anchor": 16, "evolution_validation": 8, "discovery": 16}
DEFAULT_REFS = (
    "financing_listing_action:v2", "cash_burn_rate_elevated:v1", "cash_reserves:v1",
    "cash_to_current_liabilities_ratio:v1", "gross_margin_change:v2", "liquidity_runway_months:v1",
    "net_share_retirement_yoy:v1", "operating_cash_flow_margin:v1", "revenue_acceleration:v1",
    "revenue_growth_yoy:v1", "guidance_acceleration:v1", "max_drawdown_1y:v1",
    "price_momentum_126d:v1", "negative_word_count:v1", "order_confirmation_disclosed:v1",
    "order_quality:v1", "commercialization_status:v1", "customer_concentration:v1",
)
DEFAULT_HASH = "ced3882945003998224b6b9a3c206e4bfc2f01eec6fc8857864350848a08be24"
LATEST_HASH = "40a451c051b0bfbdf424121a5362405f2fae6672c2be7b0f51e8072e8bd4ae8d"
PERIODIC_AUTHORITIES = {
    "plan.json": "fa798331e2c7bea1c636ef9af67b7a58083945b245d63f8167a799dc93d577d2",
    "input_manifest.json": "535ba9007c6b31a1b257126ce50d377536393e6df04d71ee0d751320db424f25",
    "result.json": "2c9ecb46d32fd528803fb5100c47227336d73c377903648fec55ca829cbf0a2c",
    "source-review.json": "d9dcd3066cc526b7cc3920942e93f336001e8b147fdfb565566662a0fbf29a25",
    "snapshot/reviewed_snapshot.json": "06af96e33ad7110432588763d56d2a42d3664370c2c071424a4f0b6bbd24c989",
}
_binding, _read, _tree = periodic._binding, periodic._read, periodic._tree
_check_bindings = periodic._check_bindings


@contextmanager
def _source_only():
    def forbidden(*_args, **_kwargs):
        raise ReviewedSourceRejected("LabelStore reading forbidden in frozen-case diagnostic")
    with periodic._source_only(), patch.object(LabelStore, "record", forbidden), \
            patch.object(LabelStore, "keys", forbidden), patch.object(LabelStore, "label_contract", forbidden), \
            patch.object(LabelStore, "__len__", forbidden):
        yield


def _stream_binding(path):
    path = Path(path).resolve()
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return {"path": str(path), "sha256": digest.hexdigest()}


def _aware(value):
    if not isinstance(value, str):
        raise ReviewedSourceRejected("case prediction time must retain its original string")
    try:
        instant = datetime.fromisoformat(value)
    except ValueError as exc:
        raise ReviewedSourceRejected("case prediction time is malformed") from exc
    if instant.tzinfo is None or instant.utcoffset() is None:
        raise ReviewedSourceRejected("case prediction time must be aware")
    return instant


def _project_cases(envelope, acquisition, approved, origin_binding):
    if (envelope.get("schema_version") != "diagnostic-development-subset-v1"
            or type(envelope.get("selection_seed")) is not int or envelope["selection_seed"] != 42
            or envelope.get("selection_before_model_calls") is not True
            or envelope.get("approved_manifest_hash") != APPROVED_SHA
            or approved.get("approval_status") != "human_approved"
            or approved.get("locked_test_sealed") is not True
            or envelope.get("locked_test_hash") != approved["artifacts"]["locked_test"]["sha256"]
            or acquisition.get("outcome_fields_included") is not False
            or acquisition.get("split_ownership_included") is not False):
        raise ReviewedSourceRejected("frozen cohort/approved metadata authority differs")
    splits = envelope["splits"]
    if set(splits) != set(COUNTS) or any(not isinstance(splits[key], list) or len(splits[key]) != count
                                       for key, count in COUNTS.items()):
        raise ReviewedSourceRejected("exact frozen16/8/16 split counts differ")
    cases, identities, seen = [], {}, set()
    scope_rows = acquisition["companies"]
    for split, rows in splits.items():
        for index, row in enumerate(rows):
            case_id, company_id, timestamp = row["case_id"], row["company_id"], row["prediction_time"]
            _aware(timestamp)
            if (not isinstance(case_id, str) or not case_id or case_id in seen
                    or not isinstance(company_id, str) or not re.fullmatch(r"cik_[0-9]{10}", company_id)):
                raise ReviewedSourceRejected("duplicate or invalid frozen case identity")
            seen.add(case_id)
            matches = [item for item in scope_rows if item["company_id"] == company_id]
            if len(matches) != 1:
                raise ReviewedSourceRejected("frozen company lacks unique approved acquisition identity")
            identity = matches[0]
            if identity["cik"] != company_id.removeprefix("cik_") or not isinstance(identity["symbol"], str) or not identity["symbol"]:
                raise ReviewedSourceRejected("approved company CIK/ticker differs")
            identities[company_id] = {"cik": identity["cik"], "ticker": identity["symbol"]}
            cases.append({"case_id": case_id, "company_id": company_id, "prediction_time": timestamp,
                          "split": split, "split_case_index": index, "order": len(cases)})
    projection = {"origin": origin_binding, "origin_control": {
        key: envelope[key] for key in ("schema_version", "selection_seed", "selection_before_model_calls",
                                      "approved_manifest_hash", "locked_test_hash")},
        "split_order": list(splits), "cases": cases, "identities": identities}
    _validate_projection(projection)
    return projection


def _validate_projection(projection):
    if set(projection) != {"origin", "origin_control", "split_order", "cases", "identities"}:
        raise ReviewedSourceRejected("case projection contains unsupported fields")
    controls = projection["origin_control"]
    if (set(controls) != {"schema_version", "selection_seed", "selection_before_model_calls", "approved_manifest_hash", "locked_test_hash"}
            or controls["schema_version"] != "diagnostic-development-subset-v1"
            or type(controls["selection_seed"]) is not int or controls["selection_seed"] != 42
            or controls["selection_before_model_calls"] is not True
            or controls["approved_manifest_hash"] != APPROVED_SHA
            or not re.fullmatch(r"[0-9a-f]{64}", controls["locked_test_hash"])):
        raise ReviewedSourceRejected("case projection control fields differ")
    if len(projection["split_order"]) != 3 or set(projection["split_order"]) != set(COUNTS) or len(projection["cases"]) != 40:
        raise ReviewedSourceRejected("case projection count/splits differ")
    seen, companies, observed, ordered_splits = set(), set(), {key: 0 for key in COUNTS}, []
    for order, row in enumerate(projection["cases"]):
        if set(row) != {"case_id", "company_id", "prediction_time", "split", "split_case_index", "order"}:
            raise ReviewedSourceRejected("case projection row contains unsupported fields")
        _aware(row["prediction_time"])
        split = row["split"]
        if (split not in COUNTS or type(row["order"]) is not int or row["order"] != order
                or type(row["split_case_index"]) is not int or row["split_case_index"] != observed[split]
                or not isinstance(row["case_id"], str) or not row["case_id"] or row["case_id"] in seen
                or not isinstance(row["company_id"], str) or not re.fullmatch(r"cik_[0-9]{10}", row["company_id"])):
            raise ReviewedSourceRejected("case projection order/identity differs")
        if not ordered_splits or ordered_splits[-1] != split:
            ordered_splits.append(split)
        observed[split] += 1
        seen.add(row["case_id"])
        companies.add(row["company_id"])
    if observed != COUNTS or ordered_splits != projection["split_order"] or set(projection["identities"]) != companies:
        raise ReviewedSourceRejected("case projection split scope differs")
    for company, identity in projection["identities"].items():
        if (set(identity) != {"cik", "ticker"} or identity["cik"] != company.removeprefix("cik_")
                or not isinstance(identity["ticker"], str) or not identity["ticker"]):
            raise ReviewedSourceRejected("case projection acquisition identity differs")


def _snapshot(group, output):
    if group["name"] not in {"default_v6", "latest_v12"}:
        raise ReviewedSourceRejected("unknown Registry comparison group")
    expected_version, expected_hash = (6, DEFAULT_HASH) if group["name"] == "default_v6" else (12, LATEST_HASH)
    if (type(group["version"]) is not int or group["version"] != expected_version
            or group["registry_hash"] != expected_hash or len(group["refs"]) != 18
            or len(set(group["refs"])) != 18):
        raise ReviewedSourceRejected("exact Registry version/hash/ref scope differs")
    registry_root, output = Path(group["root"]).resolve(), Path(output).resolve()
    if output.is_relative_to(registry_root) or registry_root.is_relative_to(output):
        raise ReviewedSourceRejected("diagnostic output overlaps a historical Registry")
    if not (registry_root / "registry.json").is_file():
        raise ReviewedSourceRejected("historical Registry root is missing")
    declared_version = _read(registry_root / "registry.json").get("version")
    if type(declared_version) is not int or declared_version != expected_version:
        raise ReviewedSourceRejected("historical Registry version file differs")
    registry = SignalRegistry(group["root"], candidate_root=output / "unused_candidates" / group["name"])
    snapshot = registry.snapshot_from_refs(group["version"], tuple(group["refs"]))
    if snapshot.registry_hash != group["registry_hash"]:
        raise ReviewedSourceRejected("exact Registry definition hash differs")
    bindings = [_binding(Path(group["root"]) / "registry.json")]
    for ref in group["refs"]:
        signal_id, version = ref.rsplit(":v", 1)
        manifest = registry._manifest_for(signal_id)
        directory = manifest.parent / "versions" / ("v" + version)
        bindings.extend([_binding(manifest), _binding(directory / "spec.json")])
        if ref in snapshot.skills:
            bindings.append(_binding(directory / "skill.md"))
    return snapshot, bindings


def _code_bindings():
    return periodic._code_bindings() + [_binding(Path(__file__)), _binding(OWNING_SPEC),
        _binding(Path(periodic.__file__)),
        _binding(REPO / "spec/src/stock_opportunity_agent/research/stage_contracts.md")]


def prepare(output):
    """Source-owner export of exact identities and two frozen input-only scopes."""
    with _source_only():
        return _prepare(Path(output).resolve())


def _prepare(output):
    if output.exists():
        raise ReviewedSourceRejected("frozen-case diagnostic output must be new")
    origin_binding = {"path": str(ORIGIN.resolve()), "sha256": ORIGIN_SHA}
    if _stream_binding(ORIGIN) != origin_binding:
        raise ReviewedSourceRejected("completed v182 origin hash differs")
    authorities = [{"path": str(APPROVED.resolve()), "sha256": APPROVED_SHA},
                   {"path": str(ACQUISITION.resolve()), "sha256": ACQUISITION_SHA},
                   *[{"path": str((PERIODIC_STAGE / name).resolve()), "sha256": sha}
                     for name, sha in PERIODIC_AUTHORITIES.items()]]
    _check_bindings(authorities)
    # Explicit source-owner boundary: deserialize the old mixed envelope, but
    # access only whitelisted control and identity fields, never truth/basic_info.
    projection = _project_cases(_read(ORIGIN), _read(ACQUISITION), _read(APPROVED), origin_binding)
    periodic_plan = _read(PERIODIC_STAGE / "plan.json")
    periodic_inputs = _read(PERIODIC_STAGE / "input_manifest.json")
    periodic_review = _read(periodic_inputs["source_review"]["path"])
    oracle_root = Path(periodic_review["oracle_identity"]["path"]).resolve().parent
    view_root = Path(periodic_inputs["reviewed_source_snapshot"]["root"]).resolve()
    if any(output.is_relative_to(root) or root.is_relative_to(output)
           for root in (oracle_root, view_root, PERIODIC_STAGE, ORIGIN.parent, APPROVED_ROOT)):
        raise ReviewedSourceRejected("new output overlaps a frozen source workspace")
    if (len(periodic_review["records"]) != 658
            or len(_read(view_root / "reviewed_snapshot.json")["documents"]) != 653):
        raise ReviewedSourceRejected("completed653-document source scope differs")
    latest_source = _read(periodic_plan["registry_source_inputs"]["path"])
    groups = [{"name": "default_v6", "root": str(HISTORY_REGISTRY), "version": 6,
               "registry_hash": DEFAULT_HASH, "refs": list(DEFAULT_REFS)},
              {"name": "latest_v12", "root": latest_source["registry_root"], "version": 12,
               "registry_hash": LATEST_HASH, "refs": periodic_plan["registry_refs"]}]
    for group in groups:
        _snapshot_value, group["definition_bindings"] = _snapshot(group, output)
    source_bindings = [*periodic_plan["old_source_bindings"], *periodic_plan["source_bindings"],
                      *periodic_plan["fixed_authorities"], periodic_plan["registry_source_inputs"],
                      periodic_inputs["source_review"], periodic_review["oracle_identity"]]
    for row in periodic_review["records"]:
        source_bindings.append(row["original_record"])
        source_bindings.extend(proof["artifact"] for proof in row["proofs"])
    source_bindings = sorted({b["path"]: b for b in source_bindings}.values(), key=lambda b: b["path"])
    _check_bindings(source_bindings)
    projection_path = output / "case-identities.json"
    atomic_write_json(projection_path, projection)
    plan = {"schema_version": "frozen40-source-input-plan-v1", "origin": origin_binding,
        "projection": _binding(projection_path), "metadata_authorities": authorities,
        "source_bindings": source_bindings, "old_periodic_tree": _tree(PERIODIC_STAGE),
        "reviewed_source_snapshot": periodic_inputs["reviewed_source_snapshot"], "groups": groups,
        "code_bindings": _code_bindings(), "fixed_case_denominator": 40, "per_group_resolution_denominator": 720,
        "default_basic_info_case_denominator": 40, "network_allowed": False, "model_allowed": False,
        "labels_allowed": False, "signal_apply_allowed": False, "full_prepare_allowed": False,
        "global_writes_allowed": False,
        "origin_access": "prepare source-owner deserializes mixed envelope but consumes/outputs only whitelist; execute streams bytes for whole SHA only"}
    plan["plan_hash"] = canonical_json_hash(plan)
    atomic_write_json(output / "plan.json", plan)
    return plan


def _verify_plan(output):
    plan = _read(output / "plan.json")
    if (canonical_json_hash({k: v for k, v in plan.items() if k != "plan_hash"}) != plan["plan_hash"]
            or plan["schema_version"] != "frozen40-source-input-plan-v1"
            or (plan["fixed_case_denominator"], plan["per_group_resolution_denominator"],
                plan["default_basic_info_case_denominator"]) != (40, 720, 40)
            or [group["name"] for group in plan["groups"]] != ["default_v6", "latest_v12"]
            or any(plan[key] is not False for key in ("network_allowed", "model_allowed", "labels_allowed",
                "signal_apply_allowed", "full_prepare_allowed", "global_writes_allowed"))):
        raise ReviewedSourceRejected("frozen-case plan scope/hash differs")
    if plan["origin"] != {"path": str(ORIGIN.resolve()), "sha256": ORIGIN_SHA}:
        raise ReviewedSourceRejected("fixed completed origin authority differs")
    if _stream_binding(plan["origin"]["path"]) != plan["origin"]:
        raise ReviewedSourceRejected("completed mixed origin bytes changed")
    for name in ("metadata_authorities", "source_bindings", "old_periodic_tree", "code_bindings"):
        _check_bindings(plan[name])
    for group in plan["groups"]:
        _check_bindings(group["definition_bindings"])
    _check_bindings([plan["projection"]])
    if _tree(PERIODIC_STAGE) != plan["old_periodic_tree"]:
        raise ReviewedSourceRejected("completed periodic artifacts changed")
    projection = _read(plan["projection"]["path"])
    _validate_projection(projection)
    if projection["origin"] != plan["origin"]:
        raise ReviewedSourceRejected("projection origin differs")
    return plan, projection


def execute(output):
    """Inspect fixed40 sources once; never deserialize mixed origin at execution."""
    with _source_only():
        return _execute(Path(output).resolve())


def _execute(output):
    plan, projection = _verify_plan(output)
    with (output / "execution-start.json").open("x", encoding="utf-8") as handle:
        json.dump({"plan_hash": plan["plan_hash"], "started_at": datetime.now(timezone.utc).isoformat()}, handle)
        handle.flush()
        os.fsync(handle.fileno())
    snapshots = {group["name"]: _snapshot(group, output)[0] for group in plan["groups"]}
    view = plan["reviewed_source_snapshot"]
    started = monotonic()
    store = open_raw_info_store(view["root"], reviewed_snapshot=view)
    worker = store.snapshot()
    timings = {"view_load_worker_seconds": monotonic() - started}
    resolver = _build_evidence_resolver(output / "runtime", worker,
        contract=SimpleNamespace(data_acquisition=DataAcquisitionPolicy()), allow_data_external=False, environ={}, cycle_id=1)
    executors = {name: SignalExecutor(snapshot, worker, resolver=resolver) for name, snapshot in snapshots.items()}
    summaries = {name: [] for name in snapshots}
    started = monotonic()
    for case in projection["cases"]:
        cutoff, company = _aware(case["prediction_time"]), case["company_id"]
        identity = projection["identities"][company]
        bundle = resolver.resolve_basic_info(compile_basic_info_requests(default_information_plan().basic_info_policy),
            company_id=company, identity=identity, as_of=cutoff)
        model, lineage = project_basic_info_bundle(bundle)
        atomic_write_json(output / "basic-info" / (case["case_id"] + ".json"),
            {"case": case, "bundle": bundle.to_dict(), "model": model, "lineage": lineage})
        for group in plan["groups"]:
            name = group["name"]
            resolutions = executors[name].prepare_inputs(tuple(group["refs"]), company_id=company, as_of=cutoff, identity=identity)
            ready = sum(row.status == "resolved" for row in resolutions)
            summary = {"case_id": case["case_id"], "split": case["split"], "resolved_signal_inputs": ready,
                "signal_ref_denominator": 18, "resolved_fraction": ready / 18,
                "meets_existing_0_8_signal_input_fraction": ready / 18 >= 0.8}
            atomic_write_json(output / name / "cases" / (case["case_id"] + ".json"), {"case": case,
                "registry_version": group["version"], "registry_hash": group["registry_hash"], "summary": summary,
                "exact_signal_input_resolutions": [{"signal_ref": ref, "resolution": row.to_dict()}
                    for ref, row in zip(group["refs"], resolutions, strict=True)]})
            summaries[name].append(summary)
        print(case["case_id"] + ": BasicInfo plus two independent18-ref input rows saved", flush=True)
    timings["input_only_consumers_seconds"] = monotonic() - started
    restored = open_raw_info_store(view["root"], reviewed_snapshot=view)
    if (not periodic.financial._same_document_set(worker.documents, store.documents)
            or not periodic.financial._same_document_set(restored.documents, store.documents)
            or type(worker) is not type(restored)):
        raise ReviewedSourceRejected("frozen view worker/restart canonical membership differs")
    _verify_plan(output)
    result = {"schema_version": "frozen40-source-input-result-v1", "plan_hash": plan["plan_hash"],
        "projection": plan["projection"], "fixed_case_denominator": 40, "basic_info_case_count": 40,
        "per_group_resolution_denominator": 720, "groups": {group["name"]: {
            "registry_version": group["version"], "registry_hash": group["registry_hash"], "refs": group["refs"],
            "resolved_count": sum(row["resolved_signal_inputs"] for row in summaries[group["name"]]),
            "cases_meeting_existing_0_8": sum(row["meets_existing_0_8_signal_input_fraction"] for row in summaries[group["name"]]),
            "cases": summaries[group["name"]]} for group in plan["groups"]},
        "old_sources_and_view_unchanged": True, "worker_restart_canonical_equal": True,
        "mixed_origin_bytes_accessed_for_hash": True, "mixed_origin_deserialized_during_execute": False,
        "outcome_fields_consumed_or_output": False, "LabelStore_read": False, "LockedTest_file_opened": False,
        "network_requests": 0, "model_calls": 0, "signal_apply_executed": False, "full_prepare_executed": False,
        "global_source_writes": 0, "timings": timings,
        "limitations": ["Source-owner prepare opened the mixed origin envelope; execution used its bytes only for authenticity SHA.",
            "Default v6 and latest v12 matrices are independent scope comparisons, not interchangeable passes.",
            "Missing sources and partial BasicInfo remain; resolved input status is not a valid numeric measurement or model result.",
            "This is not Fast fitness, Locked-Test performance, MVP completion or prediction benefit."]}
    atomic_write_json(output / "result.json", result)
    return result


def main():
    """Prepare identities as source owner or execute a separately frozen plan."""
    parser = argparse.ArgumentParser(description=__doc__)
    action = parser.add_mutually_exclusive_group(required=True)
    action.add_argument("--prepare", action="store_true")
    action.add_argument("--execute", action="store_true")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    value = prepare(args.output) if args.prepare else execute(args.output)
    print(json.dumps({key: value[key] for key in ("schema_version", "plan_hash")}, indent=2))


if __name__ == "__main__":
    main()
