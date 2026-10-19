"""Retain only two literal KGC operating exhibits after the prior host gate."""
from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import time
from urllib.error import HTTPError
from urllib.parse import urljoin, urlsplit
from urllib.request import Request, build_opener


ROOT = Path(__file__).resolve().parent
PLAN_SHA = "02723ead4016f6672276ffbec3ad2f14623af2e36ffa70e4bb50374b6958f04b"


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def main():
    """Fetch this fixed pair once; prior same-host stops cannot be bypassed."""
    plan_raw = (ROOT / "request-plan.json").read_bytes()
    if digest(plan_raw) != PLAN_SHA:
        raise RuntimeError("literal exhibit plan changed")
    plan = json.loads(plan_raw)
    for binding in plan["source_bindings"]:
        if digest(Path(binding["path"]).read_bytes()) != binding["sha256"]:
            raise RuntimeError("bound exhibit input changed")
    helper_spec = importlib.util.spec_from_file_location("retained_exhibit_fetch_helpers", plan["transport_helpers"]["path"])
    helper = importlib.util.module_from_spec(helper_spec)
    helper_spec.loader.exec_module(helper)
    gate = plan["required_prior_execution"]
    prior_path = Path(gate["results_path"])
    prior_raw = prior_path.read_bytes()  # Missing/unfinished v2 cannot authorize a GET.
    prior = json.loads(prior_raw)
    if (prior.get("plan_sha256") != gate["plan"]["sha256"]
            or prior.get("collector_sha256") != gate["collector"]["sha256"]
            or not prior.get("finished_at_utc") or prior.get("bound_inputs_unchanged") is not True
            or prior.get("automatic_retries") != 0 or prior.get("redirects_followed") != 0
            or prior.get("stopped_after_error") or prior.get("GET_attempts") != 2
            or any(row.get("http_status") in (403, 429) or row.get("same_host_stopped")
                   or row.get("status") in ("transport_or_retention_failed", "not_attempted_host_stopped")
                   for row in prior.get("requests", ()))):
        raise RuntimeError("v2 missing/incomplete/host-stopped/transport-failed; no exhibit GET is permitted")
    prior_plan = json.loads(helper.read_bound(gate["plan"]))
    expected = {row["name"]: row for row in prior_plan["requests"]}
    if len(prior["requests"]) != 2 or {row["name"] for row in prior["requests"]} != set(expected):
        raise RuntimeError("prior two-request identity differs")
    prior_bindings = [{"path": str(prior_path), "sha256": digest(prior_raw)}]
    for row in prior["requests"]:
        request = expected[row["name"]]
        prefix = request["kind"] == "complete_submission_header_prefix"
        path_key, hash_key = ("raw_prefix_path", "raw_prefix_sha256") if prefix else ("raw_response", "raw_sha256")
        actual_path = Path(row[path_key]).resolve()
        expected_path = prior_path.parent / (row["name"] + (".response-prefix.raw" if prefix else ".response.raw"))
        if actual_path != expected_path.resolve() or row["url"] != request["url"]:
            raise RuntimeError("prior raw receipt is outside its exact request")
        binding = {"path": str(actual_path), "sha256": row[hash_key]}
        helper.read_bound(binding)
        prior_bindings.append(binding)
    parent = helper.read_bound(plan["parent_primary"]["raw_response"]).decode("utf-8")
    if len(plan["requests"]) != 2 or plan["max_GET_attempts"] != 2:
        raise RuntimeError("exhibit count differs")
    for request in plan["requests"]:
        anchor = request["literal_parent_anchor"]
        literal = parent[anchor["start"]:anchor["end_exclusive"]]
        if (literal != anchor["raw_literal"] or not re.search(r'''href\s*=\s*["']''' + re.escape(anchor["href_raw"]) + r'''["']''', literal, re.IGNORECASE)
                or urljoin(plan["parent_primary"]["url"], anchor["href_raw"]) != request["url"]
                or request["url"].rsplit("/", 1)[0] != plan["parent_primary"]["url"].rsplit("/", 1)[0]):
            raise RuntimeError("exhibit differs from the actual same-accession parent literal")
    headers_source = json.loads(helper.read_bound(plan["headers_source"]))
    header_row = next(row for row in headers_source["requests"] if row["name"] == plan["headers_source_request_name"])
    if (set(plan["request_headers"]) != {"User-Agent", "Accept", "Accept-Encoding"}
            or {key: header_row["request_headers"][key] for key in plan["request_headers"]} != plan["request_headers"]):
        raise RuntimeError("three-key header identity differs")
    output = ROOT / "results.json"
    if output.exists() or list(ROOT.glob("*.raw")):
        raise RuntimeError("prior exhibit attempts cannot be retried or overwritten")
    result = {"schema_version": "bounded-kgc-exhibit-fetch-results-v1", "plan_sha256": PLAN_SHA,
        "collector_sha256": digest(Path(__file__).read_bytes()), "required_prior_result_bindings": prior_bindings,
        "max_GET_attempts": 2, "GET_attempts": 0, "requests": [], "automatic_retries": 0,
        "redirects_followed": 0, "source_admission": False, "source_appends": 0,
        "external_llm_calls": 0, "labels_loaded": False, "signal_apply_executed": False,
        "full_prepare_executed": False}
    helper.durable_json(output, result, initial=True)
    opener = build_opener(helper.NoRedirect())
    previous_attempt = None
    for request in plan["requests"]:
        parsed = urlsplit(request["url"])
        if (request["method"] != "GET" or parsed.scheme != "https" or parsed.hostname != "www.sec.gov"
                or parsed.username or parsed.password or parsed.query or parsed.fragment or parsed.port is not None):
            raise RuntimeError("not the exact SEC exhibit request")
        if previous_attempt is not None:
            time.sleep(max(0, 1.0 - (time.monotonic() - previous_attempt)))
        row = {"name": request["name"], "method": "GET", "url": request["url"],
            "request_headers": plan["request_headers"], "started_at_utc": datetime.now(timezone.utc).isoformat(),
            "status": "attempt_started"}
        result["GET_attempts"] += 1
        result["requests"].append(row)
        helper.durable_json(output, result)
        previous_attempt = time.monotonic()
        response = None
        try:
            try:
                response = opener.open(Request(request["url"], headers=plan["request_headers"], method="GET"), timeout=35)
            except HTTPError as error:
                response = error
            raw = response.read()
            path = ROOT / (request["name"] + ".response.raw")
            with path.open("xb") as handle:
                handle.write(raw)
                handle.flush()
                os.fsync(handle.fileno())
            row.update(status="http_response_retained", http_status=response.code,
                response_url=response.geturl(), retrieved_at_utc=datetime.now(timezone.utc).isoformat(),
                raw_response=str(path), raw_sha256=digest(raw), bytes=len(raw),
                response_headers=helper.sanitized_headers(response.headers), body_scope="not_reviewed_not_admitted")
            helper.durable_json(output, result)
            print(json.dumps({key: row[key] for key in ("name", "http_status", "bytes", "raw_sha256")}), flush=True)
            if response.code in (403, 429):
                result["stopped_same_host"] = True
                helper.durable_json(output, result)
                break
        except Exception as error:
            partial = getattr(error, "partial", None)
            if isinstance(partial, bytes) and partial:
                path = ROOT / (request["name"] + ".incomplete-retained.raw")
                with path.open("xb") as handle:
                    handle.write(partial)
                    handle.flush()
                    os.fsync(handle.fileno())
                row.update(incomplete_retained_path=str(path), incomplete_retained_sha256=digest(partial))
            row.update(status="transport_or_retention_failed", error_type=type(error).__name__, error=str(error))
            result["stopped_after_error"] = True
            helper.durable_json(output, result)
            break
        finally:
            if response is not None:
                response.close()
    for binding in [*plan["source_bindings"], *prior_bindings]:
        helper.read_bound(binding)
    result["bound_inputs_unchanged"] = True
    result["finished_at_utc"] = datetime.now(timezone.utc).isoformat()
    helper.durable_json(output, result)
    print(json.dumps({"results": str(output), "sha256": digest(output.read_bytes()),
        "GET_attempts": result["GET_attempts"], "source_admission": False}, indent=2))


if __name__ == "__main__":
    main()
