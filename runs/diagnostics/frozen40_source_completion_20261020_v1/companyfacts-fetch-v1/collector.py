"""Task-local one-attempt GPRE GET through the native managed SEC transport."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import HTTPRedirectHandler, Request, build_opener

from stock_opportunity_agent.data.raw_info import RawInfoDocument
from stock_opportunity_agent.data.sec_company_facts import validate_company_facts_response
from stock_opportunity_agent.data.sources.catalog import DataCapability
from stock_opportunity_agent.data.sources.core import DataSourceError, decode_response_text
from stock_opportunity_agent.data.sources.sec_edgar import SecEdgarClient
from stock_opportunity_agent.data.sources.state import ManagedHttpTransport, RawCacheKey, RawDataCache, RequestLedger, SourceBudget

ENDPOINT = "https://data.sec.gov/api/xbrl/companyfacts/CIK0001309402.json"
CIK = "0001309402"
ALLOWED_HEADERS = {"User-Agent", "Accept", "Accept-Encoding"}


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def bound(path):
    return {"path": str(path.resolve()), "sha256": digest(path.read_bytes())}


def write_json(path, value, *, initial=False):
    """Persist a complete receipt and fsync its directory before proceeding."""
    raw = (json.dumps(value, sort_keys=True, indent=2) + "\n").encode()
    target = path if initial else path.with_name(path.name + ".pending")
    with target.open("xb") as handle:
        handle.write(raw)
        handle.flush()
        os.fsync(handle.fileno())
    if not initial:
        os.replace(target, path)
    directory = os.open(path.parent, os.O_RDONLY)
    try:
        os.fsync(directory)
    finally:
        os.close(directory)


def read_bound(binding):
    raw = Path(binding["path"]).read_bytes()
    if digest(raw) != binding["sha256"]:
        raise RuntimeError("bound task input changed")
    return json.loads(raw)


class NoRedirect(HTTPRedirectHandler):
    """Never follow a redirect or make a replacement HTTP request."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def collect(plan_path, expected_plan_sha, *, opener=None, clock=None):
    """Execute at most one GET; an attempt marker permanently prohibits reentry."""
    clock = clock or (lambda: datetime.now(timezone.utc))
    plan_path = Path(plan_path).resolve()
    raw_plan = plan_path.read_bytes()
    if digest(raw_plan) != expected_plan_sha:
        raise RuntimeError("task plan hash differs from the approved binding")
    plan = json.loads(raw_plan)
    if (plan["schema_version"] != "gpre-companyfacts-single-fetch-v1" or plan["endpoint"] != ENDPOINT
            or plan["method"] != "GET" or plan["issuer_cik"] != CIK
            or plan["company_id"] != "cik_" + CIK or plan["timeout_seconds"] != 30
            or type(plan["max_GET_attempts"]) is not int or plan["max_GET_attempts"] != 1
            or type(plan["automatic_retries"]) is not int or plan["automatic_retries"] != 0
            or plan["redirects_allowed"] is not False or plan["collector_sha256"] != digest(Path(__file__).read_bytes())):
        raise RuntimeError("task-local singleton scope differs")
    for binding in plan["source_bindings"]:
        read_bound(binding) if binding["path"].endswith(".json") else _check_source_bytes(binding)
    headers_source = read_bound(plan["headers_source"])
    matches = [row for row in headers_source["requests"] if row.get("name") == plan["headers_source_entry"]]
    if (len(matches) != 1 or matches[0].get("http_status") != 200 or set(plan["request_headers"]) != ALLOWED_HEADERS
            or plan["request_headers"] != {key: matches[0]["request_headers"][key] for key in ALLOWED_HEADERS}
            or any(not isinstance(value, str) or not value.strip() for value in plan["request_headers"].values())):
        raise RuntimeError("approved SEC wire headers differ")
    root = plan_path.parent
    if Path(plan["output_directory"]).resolve() != root:
        raise RuntimeError("approved output directory differs; copying a plan cannot reset attempts")
    result_path, raw_path, proof_path = (root / name for name in ("results.json", "gpre-companyfacts.response.raw", "raw-response-proof.json"))
    cache_root, ledger_path, marker = root / "cache/data", root / "request-ledger.jsonl", root / ".attempt.json"
    if any(path.exists() for path in (result_path, raw_path, proof_path, cache_root, ledger_path, marker)):
        raise RuntimeError("prior attempt artifacts prohibit reentry")
    started = clock()
    if started.tzinfo is None or started.utcoffset() is None:
        raise RuntimeError("attempt clock must be aware")
    entry = {"name": "gpre-companyfacts", "method": "GET", "url": ENDPOINT,
        "request_headers": plan["request_headers"], "started_at_utc": started.isoformat(), "status": "attempt_recorded_before_network"}
    result = {"schema_version": "gpre-companyfacts-single-fetch-result-v1", "plan_sha256": expected_plan_sha,
        "collector_sha256": plan["collector_sha256"], "attempt_reservations": 1, "GET_attempts": 0,
        "network_open_calls": 0, "HTTP_responses_retained": 0, "max_GET_attempts": 1,
        "automatic_retries": 0, "redirects_followed": 0, "terminal": False, "requests": [entry],
        "source_appends": 0, "typed_products_materialized": 0, "labels_loaded": False, "external_llm_calls": 0}
    write_json(marker, {"plan_sha256": expected_plan_sha, "started_at_utc": started.isoformat(), "reentry_forbidden": True}, initial=True)
    write_json(result_path, result, initial=True)

    class ReceiptTransport:
        """Use frozen three-header wire policy; retain the actual single response."""

        def get_json(self, url, headers):
            try:
                return self.fetch_json(url, headers)
            except Exception as error:
                entry["validation_or_transport_failure_type"] = type(error).__name__
                # Native ledger messages must not inherit arbitrary opener/body
                # exception text; retain the typed failure and HTTP receipt only.
                raise DataSourceError("SEC single response failed: " + type(error).__name__) from None

        def fetch_json(self, url, headers):
            if url != ENDPOINT or headers.get("User-Agent") != plan["request_headers"]["User-Agent"]:
                raise DataSourceError("unexpected native SEC request")
            # Native SEC client negotiates compression; this task instead sends
            # exactly the three already-successful, explicitly frozen wire headers.
            request = Request(ENDPOINT, headers=plan["request_headers"], method="GET")
            active_opener = opener if opener is not None else build_opener(NoRedirect())
            open_response = active_opener.open
            result.update(GET_attempts=1, network_open_calls=1)
            entry["status"] = "network_open_started"
            write_json(result_path, result)
            try:
                response = open_response(request, timeout=30)
            except HTTPError as error:
                response = error
            with response:
                body_bytes = response.read()
                response_headers = {key: value for key, value in response.headers.items()
                    if not any(part in key.lower() for part in ("auth", "cookie", "key", "token", "secret", "password"))}
                retrieved = clock()
                entry.update(status="http_response_retained", http_status=response.status, response_url=response.geturl(),
                    retrieved_at_utc=retrieved.isoformat(), response_headers=response_headers,
                    raw_response=str(raw_path), raw_sha256=digest(body_bytes), bytes=len(body_bytes))
                result["HTTP_responses_retained"] = 1
                with raw_path.open("xb") as handle:
                    handle.write(body_bytes)
                    handle.flush()
                    os.fsync(handle.fileno())
                write_json(result_path, result)
                if response.status != 200 or response.geturl() != ENDPOINT or retrieved < started:
                    raise DataSourceError("SEC HTTP status, response URL or clock rejected")
                encoding = response.headers.get("Content-Encoding")
                payload = json.loads(decode_response_text(body_bytes, encoding))
                validate_company_facts_response(payload, CIK)  # before native cache write
                return payload

    try:
        cache, ledger = RawDataCache(cache_root), RequestLedger(ledger_path)
        budget = SourceBudget(ledger)
        assert budget.quotas["sec_edgar"].per_second_limit == 10
        managed = ManagedHttpTransport("sec_edgar", DataCapability.FINANCIAL_STATEMENTS,
            ReceiptTransport(), cache, ledger, budget, clock=clock)
        payload = SecEdgarClient(plan["request_headers"]["User-Agent"], transport=managed).company_facts(CIK)
        key = RawCacheKey.from_request("sec_edgar", DataCapability.FINANCIAL_STATEMENTS, "GET", ENDPOINT)
        cached = cache.get(key)
        normalized_at = clock()
        if cached is None or normalized_at < cached.retrieved_at or cached.retrieved_at < datetime.fromisoformat(entry["retrieved_at_utc"]):
            raise RuntimeError("cache/proof native clocks are not ordered")
        content = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
        proof = RawInfoDocument.create(document_id="sec_edgar:cik_" + CIK + ":sec_company_facts_raw_response:" + digest(content.encode())[:24],
            company_id="cik_" + CIK, source_type="sec_company_facts_raw_response", published_at=normalized_at,
            available_at=normalized_at, content=content, metadata={"provider": "sec_edgar", "cik": CIK})
        write_json(proof_path, proof.to_dict(), initial=True)
        result.update(terminal=True, status="successful", native_cache=bound(cache_root / "sec_edgar/financial_statements" / (key.digest + ".json")),
            raw_response_proof=bound(proof_path), native_ledger=bound(ledger_path), cache_retrieved_at=cached.retrieved_at.isoformat(),
            proof_normalized_at=normalized_at.isoformat(), finished_at_utc=clock().isoformat())
        write_json(result_path, result)
        return result
    except Exception as error:
        entry["failure_type"] = type(error).__name__
        if entry["status"] in {"attempt_recorded_before_network", "network_open_started"}:
            entry["status"] = "transport_or_native_failure"
        result.update(terminal=True, status="failed", finished_at_utc=clock().isoformat())
        write_json(result_path, result)
        raise


def _check_source_bytes(binding):
    if digest(Path(binding["path"]).read_bytes()) != binding["sha256"]:
        raise RuntimeError("bound native source changed")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--plan", type=Path, required=True)
    parser.add_argument("--expected-plan-sha", required=True)
    parser.add_argument("--execute", action="store_true", required=True)
    args = parser.parse_args()
    collect(args.plan, args.expected_plan_sha)
