"""Fetch one exact annual primary and one bounded submission-header prefix."""
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
from urllib.parse import urlsplit
from urllib.request import Request, build_opener


ROOT = Path(__file__).resolve().parent
PLAN_SHA = "9c5354f0f2455ad45caf43f9c8079e345e3897a09deeccdb59b90e4ecb78d4a2"


def _digest(raw):
    return hashlib.sha256(raw).hexdigest()


def _header_fields(raw, expected):
    """Extract literal fields only from a complete retained SEC header."""
    end = raw.upper().find(b"</SEC-HEADER>")
    if end < 0:
        return {"SEC_header_end_present": False, "identity_matches_plan": False}
    header = raw[:end + len(b"</SEC-HEADER>")].decode("ascii", errors="replace")
    def match(pattern):
        found = re.search(pattern, header, re.IGNORECASE)
        return found.group(1).strip() if found else None
    fields = {
        "acceptance_datetime_token": match(r"<ACCEPTANCE-DATETIME>\s*(\d{14})"),
        "accession_number": match(r"ACCESSION NUMBER:\s*(\d{10}-\d{2}-\d{6})"),
        "submission_type": match(r"CONFORMED SUBMISSION TYPE:\s*([^\r\n]+)"),
        "filed_as_of_date_token": match(r"FILED AS OF DATE:\s*(\d{8})"),
        "conformed_period_of_report_token": match(r"CONFORMED PERIOD OF REPORT:\s*(\d{8})"),
        "issuer_cik_tokens": re.findall(r"CENTRAL INDEX KEY:\s*(\d{10})", header, re.IGNORECASE),
    }
    return {"SEC_header_end_present": True, "header_fields": fields,
        "identity_matches_plan": fields["accession_number"] == expected["accession_number"]
            and fields["submission_type"] == expected["form"]
            and expected["issuer_cik"] in fields["issuer_cik_tokens"],
        "acceptance_timezone_interpretation": "none_literal_token_only"}


def main():
    """Execute this two-request plan once; never infer admission from a prefix."""
    raw_plan = (ROOT / "request-plan.json").read_bytes()
    if _digest(raw_plan) != PLAN_SHA:
        raise RuntimeError("annual/header request plan differs")
    plan = json.loads(raw_plan)
    for binding in plan["source_bindings"]:
        if _digest(Path(binding["path"]).read_bytes()) != binding["sha256"]:
            raise RuntimeError("bound source changed: " + binding["path"])
    helper_binding = plan["transport_helpers"]
    spec = importlib.util.spec_from_file_location("retained_periodic_fetch_helpers", helper_binding["path"])
    helper = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(helper)
    if (len(plan["requests"]) != 2 or plan["max_GET_attempts"] != 2
            or plan["automatic_retries"] != 0 or plan["redirects_allowed"] is not False):
        raise RuntimeError("two-request boundary differs")
    source_receipts = json.loads(helper.read_bound(plan["headers_source"]))
    source_rows = [row for row in source_receipts["requests"]
                   if row["name"] == plan["headers_source_request_name"]]
    if (len(source_rows) != 1 or set(plan["request_headers"]) != {"User-Agent", "Accept", "Accept-Encoding"}
            or {key: source_rows[0]["request_headers"][key] for key in plan["request_headers"]} != plan["request_headers"]):
        raise RuntimeError("request headers differ from retained three-key receipt")
    output = ROOT / "results.json"
    if output.exists() or list(ROOT.glob("*.raw")):
        raise RuntimeError("prior attempts/raw bytes prohibit overwrite or retry")
    result = {"schema_version": "bounded-periodic-annual-header-results-v1", "plan_sha256": PLAN_SHA,
        "collector_sha256": _digest(Path(__file__).read_bytes()), "max_GET_attempts": 2,
        "GET_attempts": 0, "requests": [], "automatic_retries": 0, "redirects_followed": 0,
        "external_llm_calls": 0, "source_appends": 0, "source_admission": False,
        "clock_or_policy_changes": False, "labels_loaded": False, "signal_apply_executed": False,
        "full_prepare_executed": False}
    helper.durable_json(output, result, initial=True)
    opener = build_opener(helper.NoRedirect())
    host_blocked = False
    previous_attempt = None
    for request in plan["requests"]:
        parsed = urlsplit(request["url"])
        if (request["method"] != "GET" or parsed.scheme != "https" or parsed.hostname != "www.sec.gov"
                or parsed.username or parsed.password or parsed.query or parsed.fragment or parsed.port is not None):
            raise RuntimeError("request is not the frozen SEC static endpoint")
        if host_blocked:
            result["requests"].append({"name": request["name"], "url": request["url"],
                "status": "not_attempted_host_stopped", "GET_attempts": 0})
            helper.durable_json(output, result)
            continue
        if previous_attempt is not None:
            time.sleep(max(0, plan["minimum_seconds_between_GET_attempts"] - (time.monotonic() - previous_attempt)))
        prefix = request["kind"] == "complete_submission_header_prefix"
        headers = dict(plan["request_headers"])
        if prefix:
            if request["request_range"] != "bytes=0-65535" or request["max_retained_response_bytes"] != 65536:
                raise RuntimeError("header prefix boundary differs")
            headers["Range"] = request["request_range"]
        row = {"name": request["name"], "method": "GET", "url": request["url"], "request_headers": headers,
            "started_at_utc": datetime.now(timezone.utc).isoformat(), "status": "attempt_started",
            "retention_kind": "prefix_only" if prefix else "full_response"}
        result["GET_attempts"] += 1
        result["requests"].append(row)
        helper.durable_json(output, result)
        previous_attempt = time.monotonic()
        response = None
        try:
            try:
                response = opener.open(Request(request["url"], headers=headers, method="GET"), timeout=35)
            except HTTPError as error:
                response = error
            raw = response.read(request["max_retained_response_bytes"]) if prefix else response.read()
            path = ROOT / (request["name"] + (".response-prefix.raw" if prefix else ".response.raw"))
            with path.open("xb") as handle:
                handle.write(raw)
                handle.flush()
                os.fsync(handle.fileno())
            row.update(http_status=response.code, response_url=response.geturl(),
                retrieved_at_utc=datetime.now(timezone.utc).isoformat(),
                response_headers=helper.sanitized_headers(response.headers))
            if prefix:
                row.update(status="http_response_prefix_retained", raw_prefix_path=str(path),
                    raw_prefix_sha256=_digest(raw), retained_bytes=len(raw),
                    max_retained_response_bytes=65536, full_submission_hash_claimed=False,
                    retention="Only exact retained prefix bytes, even if the server ignored Range.")
                if response.code in (200, 206):
                    row.update(_header_fields(raw, plan["target"]))
            else:
                row.update(status="http_response_retained", raw_response=str(path),
                    raw_sha256=_digest(raw), bytes=len(raw), body_scope="not_reviewed_not_admitted")
            if response.code in (403, 429):
                host_blocked = True
                row["same_host_stopped"] = True
            helper.durable_json(output, result)
            print(json.dumps({key: value for key, value in row.items() if key in
                {"name", "http_status", "raw_sha256", "bytes", "raw_prefix_sha256", "retained_bytes", "SEC_header_end_present", "identity_matches_plan"}}), flush=True)
        except Exception as error:
            partial = getattr(error, "partial", None)
            if isinstance(partial, bytes) and partial:
                partial = partial[:65536] if prefix else partial
                path = ROOT / (request["name"] + ".incomplete-retained.raw")
                with path.open("xb") as handle:
                    handle.write(partial)
                    handle.flush()
                    os.fsync(handle.fileno())
                row.update(incomplete_retained_path=str(path), incomplete_retained_sha256=_digest(partial),
                    incomplete_retained_bytes=len(partial), full_submission_hash_claimed=False)
            row.update(status="transport_or_retention_failed", error_type=type(error).__name__, error=str(error))
            result["stopped_after_error"] = True
            helper.durable_json(output, result)
            break
        finally:
            if response is not None:
                response.close()
    for binding in plan["source_bindings"]:
        helper.read_bound(binding)
    result["bound_inputs_unchanged"] = True
    result["finished_at_utc"] = datetime.now(timezone.utc).isoformat()
    helper.durable_json(output, result)
    print(json.dumps({"results": str(output), "sha256": _digest(output.read_bytes()),
        "GET_attempts": result["GET_attempts"], "source_admission": False}, indent=2))


if __name__ == "__main__":
    main()
