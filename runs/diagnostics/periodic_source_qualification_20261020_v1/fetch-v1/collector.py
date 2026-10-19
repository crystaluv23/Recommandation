"""Collect at most three pre-reviewed exact SEC URLs once, without retries."""
from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import time
from urllib.error import HTTPError
from urllib.parse import urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener


ROOT = Path(__file__).resolve().parent
PLAN_SHA = "11800c79f50246305e2b91bd44cb90bafe1c068950170d5db0130c8b5ed3acde"
ALLOWED_HEADERS = {"User-Agent", "Accept", "Accept-Encoding"}


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def read_bound(binding):
    raw = Path(binding["path"]).read_bytes()
    if digest(raw) != binding["sha256"]:
        raise RuntimeError("frozen SEC fetch input changed: " + binding["path"])
    return raw


def durable_json(path, value, *, initial=False):
    raw = (json.dumps(value, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
    if initial:
        with path.open("xb") as handle:
            handle.write(raw)
            handle.flush()
            os.fsync(handle.fileno())
    else:
        temporary = path.with_name(path.name + ".pending")
        with temporary.open("wb") as handle:
            handle.write(raw)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    descriptor = os.open(path.parent, os.O_RDONLY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def sanitized_headers(headers):
    hidden = {"authorization", "proxy-authorization", "cookie", "set-cookie", "x-api-key"}
    return {key: "[REDACTED_SECRET]" if key.lower() in hidden else value
            for key, value in headers.items()}


class NoRedirect(HTTPRedirectHandler):
    """Retain redirect responses without making another request."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def main():
    """Execute only this frozen plan; durable prior attempts prohibit rerun."""
    plan_raw = (ROOT / "request-plan.json").read_bytes()
    if digest(plan_raw) != PLAN_SHA:
        raise RuntimeError("SEC fetch plan bytes differ from the reviewed plan")
    plan = json.loads(plan_raw)
    if (plan["schema_version"] != "bounded-periodic-primary-fetch-v1"
            or not 2 <= len(plan["requests"]) <= 3
            or plan["max_GET_attempts"] != len(plan["requests"])
            or plan["automatic_retries"] != 0 or plan["redirects_allowed"] is not False
            or set(plan["request_headers"]) != ALLOWED_HEADERS):
        raise RuntimeError("SEC fetch scope differs")
    for binding in plan["source_bindings"]:
        read_bound(binding)
    header_source = json.loads(read_bound(plan["headers_source"]))
    header_rows = [row for row in header_source["requests"]
                   if row["name"] == plan["headers_source_request_name"]]
    if (len(header_rows) != 1 or {name: header_rows[0]["request_headers"][name]
                                for name in ALLOWED_HEADERS} != plan["request_headers"]):
        raise RuntimeError("headers differ from the retained SEC receipt")
    names, urls = set(), set()
    for row in plan["requests"]:
        parsed = urlsplit(row["url"])
        if (row["method"] != "GET" or row["name"] in names or row["url"] in urls
                or parsed.scheme != "https" or parsed.hostname not in {"www.sec.gov", "data.sec.gov"}
                or parsed.query or parsed.fragment or parsed.username or parsed.password
                or parsed.port is not None):
            raise RuntimeError("duplicate or non-SEC exact request")
        names.add(row["name"])
        urls.add(row["url"])
    output = ROOT / "results.json"
    if output.exists() or list(ROOT.glob("*.response.raw")):
        raise RuntimeError("existing SEC attempts or raw bytes cannot be overwritten/retried")
    result = {"schema_version": "bounded-periodic-primary-fetch-result-v1", "plan_sha256": PLAN_SHA,
        "collector_sha256": digest(Path(__file__).read_bytes()), "max_GET_attempts": plan["max_GET_attempts"],
        "GET_attempts": 0, "requests": [], "automatic_retries": 0, "redirects_followed": 0,
        "external_llm_calls": 0, "source_appends": 0, "source_admission": False,
        "labels_loaded": False, "signal_apply_executed": False, "full_prepare_executed": False}
    durable_json(output, result, initial=True)
    opener = build_opener(NoRedirect())
    blocked_hosts = set()
    previous_attempt = None
    for request in plan["requests"]:
        host = urlsplit(request["url"]).hostname
        if host in blocked_hosts:
            result["requests"].append({"name": request["name"], "url": request["url"],
                "status": "not_attempted_host_stopped", "GET_attempts": 0})
            durable_json(output, result)
            continue
        if previous_attempt is not None:
            time.sleep(max(0, plan["minimum_seconds_between_GET_attempts"] - (time.monotonic() - previous_attempt)))
        row = {"name": request["name"], "method": "GET", "url": request["url"],
            "request_headers": plan["request_headers"], "started_at_utc": datetime.now(timezone.utc).isoformat(),
            "status": "attempt_started"}
        result["GET_attempts"] += 1
        result["requests"].append(row)
        durable_json(output, result)  # Must precede the connection, including a failed one.
        previous_attempt = time.monotonic()
        response = None
        try:
            try:
                response = opener.open(Request(request["url"], headers=plan["request_headers"], method="GET"),
                    timeout=plan["timeout_seconds"])
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
                response_headers=sanitized_headers(response.headers),
                semantic_body_scope="not_reviewed_no_admission")
            if response.code in (403, 429):
                blocked_hosts.add(host)
                row["same_host_stopped"] = True
            if response.code == 200 and request.get("kind") == "linked_annual_submissions_archive":
                try:
                    archive = json.loads(raw)
                    target = plan["annual_pointer"]["target"]
                    fields = ("accessionNumber", "filingDate", "form", "reportDate", "primaryDocument", "acceptanceDateTime")
                    lengths = {key: len(archive[key]) for key in fields
                               if isinstance(archive.get(key), list)}
                    indices = [i for i, value in enumerate(archive.get("accessionNumber", ()))
                               if value == target["accession_number"]]
                    matched_rows = [{key: archive[key][index] for key in fields}
                                    for index in indices if all(index < lengths.get(key, 0) for key in fields)]
                    row["annual_target_check"] = {"parallel_array_lengths": lengths,
                        "equal_required_arrays": len(lengths) == len(fields) and len(set(lengths.values())) == 1,
                        "unique_accession_matches": len(indices),
                        "rows": matched_rows,
                        "target_identity_equal": len(matched_rows) == 1 and all(matched_rows[0][name] == target[key]
                            for name, key in (("accessionNumber", "accession_number"), ("filingDate", "filing_date"),
                                              ("form", "form"), ("reportDate", "period_end"))),
                        "root_declared_entry": plan["annual_pointer"]["unique_link_entry"],
                        "actual_filing_date_min": min(archive["filingDate"]) if lengths.get("filingDate") else None,
                        "actual_filing_date_max": max(archive["filingDate"]) if lengths.get("filingDate") else None}
                except (ValueError, TypeError, KeyError) as error:
                    row["annual_target_check"] = {"status": "invalid_archive_shape", "error_type": type(error).__name__}
            durable_json(output, result)
            print(json.dumps({key: row[key] for key in ("name", "http_status", "bytes", "raw_sha256")}), flush=True)
        except Exception as error:
            partial = getattr(error, "partial", None)
            if isinstance(partial, bytes) and partial:
                partial_path = ROOT / (request["name"] + ".response.partial.raw")
                with partial_path.open("xb") as handle:
                    handle.write(partial)
                    handle.flush()
                    os.fsync(handle.fileno())
                row.update(partial_response=str(partial_path), partial_sha256=digest(partial), partial_bytes=len(partial))
            row.update(status="transport_or_retention_failed", error_type=type(error).__name__, error=str(error),
                retrieved_at_utc=datetime.now(timezone.utc).isoformat())
            result["stopped_after_error"] = True
            durable_json(output, result)
            break
        finally:
            if response is not None:
                response.close()
    for binding in plan["source_bindings"]:
        read_bound(binding)
    result["bound_inputs_unchanged"] = True
    result["finished_at_utc"] = datetime.now(timezone.utc).isoformat()
    durable_json(output, result)
    print(json.dumps({"results": str(output), "sha256": digest(output.read_bytes()),
        "GET_attempts": result["GET_attempts"], "source_admission": False}, indent=2))


if __name__ == "__main__":
    main()
