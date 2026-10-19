"""One filename census, then only fixed25 exact-request cache candidates; no admission."""
from collections import defaultdict
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import subprocess
from urllib.parse import parse_qsl, quote, urlencode, urlsplit, urlunsplit

from stock_opportunity_agent.data.sources.catalog import DataCapability
from stock_opportunity_agent.data.sources.state import RawCacheKey

ROOT = Path(__file__).resolve().parents[3]
OUTPUT = Path(__file__).with_name("local-cache-chain-inventory.json")
INPUT = ROOT / "runs/diagnostics/reviewed_frozen_case_inputs_20261020_v1/remaining-source-candidate-inventory.json"
INPUT_SHA = "6d9d804e782e2de33b6365caff7033ffd09d5d6ecf9281f397af8f3c40d9717b"


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def sensitive(key):
    return any(part in str(key).lower() for part in ("key", "token", "secret", "password", "auth", "signature"))


def sanitized_url(value):
    if not isinstance(value, str):
        return None
    url = urlsplit(value)
    host = url.hostname or ""
    if url.port is not None:
        host += ":" + str(url.port)
    return urlunsplit((url.scheme, host, url.path, urlencode([(k, v) for k, v in parse_qsl(url.query, keep_blank_values=True) if not sensitive(k)]), ""))


def instant(value):
    try:
        result = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        return result if result.tzinfo and result.utcoffset() is not None else None
    except (TypeError, ValueError):
        return None


def cik(value):
    if type(value) is int and 0 < value < 10**10:
        return str(value).zfill(10)
    if isinstance(value, str) and re.fullmatch(r"[0-9]{1,10}", value.strip()) and int(value.strip()) > 0:
        return value.strip().zfill(10)
    return None


def main():
    """Inventory existing exact cache variants without choosing a favorable vintage."""
    assert not OUTPUT.exists(), "existing candidate inventory must not be overwritten"
    original_input = INPUT.read_bytes()
    assert digest(original_input) == INPUT_SHA
    prior = json.loads(original_input)
    cases = prior["cases"]
    assert len(cases) == 25 and sum(c["split"] != "anchor" for c in cases) == 24
    wanted = {}

    def request(family, case, endpoint, source, capability, originals=()):
        key = RawCacheKey.from_request(source, capability, "GET", endpoint)
        identity = (family, case["case_id"], key.digest)
        if identity in wanted:
            wanted[identity]["originals"].extend(originals)
            return
        wanted[identity] = {"family": family, "case_id": case["case_id"], "company_id": case["company_id"],
            "ticker": case["ticker"], "cutoff": case["prediction_time"], "cache_key": key.digest,
            "endpoint": key.endpoint, "params": list(map(list, key.params)), "source": source,
            "capability": capability.value, "originals": list(originals), "matches": []}

    for case in cases:
        issuer = case["company_id"].removeprefix("cik_")
        request("companyfacts", case, "https://data.sec.gov/api/xbrl/companyfacts/CIK" + issuer + ".json",
            "sec_edgar", DataCapability.FINANCIAL_STATEMENTS, case["sources"]["sec_company_facts_raw_response"])
        request("submissions_root", case, "https://data.sec.gov/submissions/CIK" + issuer + ".json",
            "sec_edgar", DataCapability.FILING_DOCUMENTS, case["sources"]["filing"])
        for original in case["sources"]["filing"]:
            endpoint = original["safe_source_metadata"].get("source_url")
            if endpoint:
                request("filing_body", case, endpoint, "sec_edgar", DataCapability.FILING_DOCUMENTS, (original,))
        for original in case["sources"]["market_data"]:
            meta = original["safe_source_metadata"]
            if all(isinstance(meta.get(k), str) and meta[k] for k in ("symbol", "start", "end")):
                endpoint = ("https://api.massive.com/v2/aggs/ticker/" + quote(meta["symbol"], safe="")
                    + "/range/1/day/" + meta["start"] + "/" + meta["end"] + "?adjusted=true&sort=asc&limit=50000")
                request("market_daily", case, endpoint, "massive", DataCapability.PRICE_DAILY, (original,))

    command = ["rg", "--files", "--hidden", "--no-ignore", str(ROOT / "runs/cold_start")]
    census = subprocess.run(command, check=True, capture_output=True).stdout
    by_name = defaultdict(list)
    wanted_names = {r["cache_key"] + ".json" for r in wanted.values()}
    filenames = census.decode().splitlines()
    for filename in filenames:
        path = Path(filename)
        if path.name in wanted_names and "/cache/data/" in path.as_posix():
            by_name[path.name].append(path)
    read_bindings = {}
    for item in wanted.values():
        item["original_candidates"] = [{k: original[k] for k in (
            "original_record", "document_id", "source_type", "content_hash", "published_at", "available_at", "safe_source_metadata")}
            for original in item["originals"]]
        originals = []
        for original in item["originals"]:
            binding = original["original_record"]
            raw = Path(binding["path"]).read_bytes()
            read_bindings[binding["path"]] = digest(raw)
            document = json.loads(raw)
            originals.append((original, document, digest(raw) == binding["sha256"]))
        for path in sorted(by_name[item["cache_key"] + ".json"]):
            raw = path.read_bytes()
            sha = digest(raw)
            read_bindings[str(path)] = sha
            row = {"binding": {"path": str(path), "sha256": sha}, "status": "candidate_not_verified"}
            try:
                envelope = json.loads(raw)
                body = envelope.get("body")
                row.update(sanitized_endpoint=sanitized_url(envelope.get("endpoint")),
                    sanitized_params=[[str(k), str(v)] for k, v in envelope.get("params", []) if not sensitive(k)],
                    source_key=envelope.get("source_key"), capability=envelope.get("capability"),
                    payload_kind=envelope.get("payload_kind"), retrieved_at=envelope.get("retrieved_at"),
                    request_identity_exact=envelope.get("endpoint") == item["endpoint"]
                        and envelope.get("params") == item["params"] and envelope.get("source_key") == item["source"]
                        and envelope.get("capability") == item["capability"])
                row["response_body_canonical_sha256"] = digest(json.dumps(body, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode())
                if item["family"] == "companyfacts":
                    text = json.dumps(body, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
                    row["response_cik"] = cik(body.get("cik")) if isinstance(body, dict) else None
                    row["issuer_matches_case"] = row["response_cik"] == item["company_id"].removeprefix("cik_")
                    row["whole_raw_comparisons"] = [{"original_record": o["original_record"],
                        "original_binding_unchanged": unchanged, "document_id": d["document_id"],
                        "whole_raw_equals_cache_body": d.get("content") == text,
                        "cache_not_after_old_normalization": instant(envelope.get("retrieved_at")) <= instant(d.get("available_at"))
                            if instant(envelope.get("retrieved_at")) and instant(d.get("available_at")) else None}
                        for o, d, unchanged in originals]
                elif item["family"] == "submissions_root":
                    row["response_cik"] = cik(body.get("cik")) if isinstance(body, dict) else None
                    row["issuer_matches_case"] = row["response_cik"] == item["company_id"].removeprefix("cik_")
                    arrays = body.get("filings", {}).get("recent", {}) if isinstance(body, dict) else {}
                    accessions = arrays.get("accessionNumber", [])
                    row["root_recent_count"] = len(accessions) if isinstance(accessions, list) else None
                    row["root_linked_history_count"] = len(body.get("filings", {}).get("files", [])) if isinstance(body, dict) else None
                    targets = []
                    for o, d, unchanged in originals:
                        accn = o["safe_source_metadata"].get("accession_number")
                        indices = [i for i, x in enumerate(accessions) if x == accn] if isinstance(accessions, list) else []
                        fields = [{k: arrays[k][i] for k in ("accessionNumber", "form", "primaryDocument", "filingDate", "reportDate", "acceptanceDateTime")
                            if isinstance(arrays.get(k), list) and i < len(arrays[k])} for i in indices]
                        targets.append({"document_id": d["document_id"], "original_binding_unchanged": unchanged,
                            "exact_target_matches": len(indices), "retained_target_fields": fields,
                            "accepted_matches_original": len(fields) == 1 and instant(fields[0].get("acceptanceDateTime")) == instant(d.get("available_at"))
                                if fields and instant(fields[0].get("acceptanceDateTime")) else None})
                    row["original_target_comparisons"] = targets
                elif item["family"] == "filing_body":
                    row["whole_original_comparisons"] = [{"document_id": d["document_id"],
                        "original_binding_unchanged": unchanged, "whole_body_equals_original": body == d.get("content")}
                        for o, d, unchanged in originals]
                else:
                    row["response_symbol"] = body.get("ticker") if isinstance(body, dict) else None
                    row["response_adjusted"] = body.get("adjusted") if isinstance(body, dict) else None
                    row["response_status"] = body.get("status") if isinstance(body, dict) else None
                    row["response_bar_count"] = len(body["results"]) if isinstance(body, dict) and isinstance(body.get("results"), list) else None
                    row["historical_issuer_split_and_production_reconstruction"] = "not_verified_or_newly_queried"
            except (ValueError, TypeError, AttributeError, KeyError, OverflowError) as exc:
                row.update(status="unknown_malformed_exact_key_candidate", error_type=type(exc).__name__)
            item["matches"].append(row)
        item.pop("originals")
    case_rows = []
    for case in cases:
        requests = [r for r in wanted.values() if r["case_id"] == case["case_id"]]
        cf = next(r for r in requests if r["family"] == "companyfacts")
        good = [r for r in cf["matches"] if r.get("request_identity_exact") and r.get("issuer_matches_case")
            and any(v["whole_raw_equals_cache_body"] and v["original_binding_unchanged"] for v in r.get("whole_raw_comparisons", []))]
        case_rows.append({k: case[k] for k in ("case_id", "company_id", "ticker", "split", "prediction_time")}
            | {"companyfacts_exact_request_candidates": len(cf["matches"]),
                "companyfacts_matching_whole_raw_candidate_count": len(good),
                "companyfacts_distinct_response_bodies": len({m.get("response_body_canonical_sha256") for m in cf["matches"]}),
                "prior_chain_inputs_located": case["companyfacts"]["chain_status"].startswith("cache_and"),
                "requests": requests, "verdict": "unknown_candidates_only_no_admission"})
    assert INPUT.read_bytes() == original_input
    for filename, sha in read_bindings.items():
        assert digest(Path(filename).read_bytes()) == sha, "a read input changed during inventory"
    source_files = [Path(__file__), ROOT / "src/stock_opportunity_agent/data/sources/state.py",
        ROOT / "src/stock_opportunity_agent/data/sources/catalog.py"]
    result = {"schema_version": "fixed25-cross-root-cache-chain-candidates-v1", "prior_inventory": {"path": str(INPUT), "sha256": INPUT_SHA},
        "scope": "One filename-only all-cold_start census; content reads only fixed25 exact request digest cache filenames and their already-bound originals. No archive-page search, cache-content scan, qualification or normalization.",
        "filename_census": {"command": command, "command_invocations": 1, "hidden_included": True, "ignore_rules_disabled": True,
            "path_count": len(filenames), "stdout_sha256": digest(census)},
        "summary": {"fixed_cases": 25, "exact_request_keys": len(wanted), "unique_exact_cache_files_read": len({str(p) for values in by_name.values() for p in values}),
            "prior_cases_with_matching_cf_inputs": sum(c["prior_chain_inputs_located"] for c in case_rows),
            "now_cases_with_matching_cf_inputs": sum(c["companyfacts_matching_whole_raw_candidate_count"] > 0 for c in case_rows),
            "GET_model_LabelStore_LockedTest_normalization_append_admission_calls": 0},
        "cases": case_rows, "all_read_existing_file_hashes_unchanged": True,
        "read_file_bindings": [{"path": filename, "sha256": sha} for filename, sha in sorted(read_bindings.items())],
        "code_bindings": [{"path": str(p), "sha256": digest(p.read_bytes())} for p in source_files],
        "limitations": ["All matching cache versions retained, including mismatches; none selected for admission.",
            "Cache/raw co-location does not prove trustworthy source, source policy, full content scope, Signal readiness or research benefit.",
            "Different retrieval/body/identity/clock observations remain explicit; no source times or originals changed.",
            "Only fixed request keys were sought. Other requests, history pages and source families remain outside this lookup.",
            "Original candidates came from only financials/sec_company_facts_raw_response/sec_company_facts/market_data/filing namespaces; filing0 is not an absence proof for operating originals in sec_filing or exact-form namespaces.",
            "The202 existing filing-body keys, including8-Ks, do not establish sufficient annual/interim operating content. Latest eligible annual/interim selection and any missing precise body key remain a separate bounded follow-up."]}
    with OUTPUT.open("x") as handle:
        json.dump(result, handle, indent=2, ensure_ascii=False)
        handle.write("\n")
    print(json.dumps({"path": str(OUTPUT), "sha256": digest(OUTPUT.read_bytes()), "summary": result["summary"], "filename_count": len(filenames)}))


if __name__ == "__main__":
    main()
