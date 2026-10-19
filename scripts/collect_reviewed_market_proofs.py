"""Collect the frozen bounded historical-issuer and split GET proofs only."""
from __future__ import annotations

import argparse
from datetime import date, datetime, timezone
import fcntl
import hashlib
import json
import math
import os
from pathlib import Path
import re
import time
from urllib.error import HTTPError
from urllib.parse import urlencode
from urllib.request import build_opener, HTTPRedirectHandler, Request

from stock_opportunity_agent.artifacts import atomic_write_json

INVENTORY_SHA256 = "cd20f162f7d7bd04d0340732bd0b19262b9aad6e03f06594d72fc909a35f2183"


def _sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def _read(path):
    return json.loads(Path(path).read_text())


def _requests(inventory):
    if _sha(inventory) != INVENTORY_SHA256:
        raise ValueError("inventory binding differs")
    value, bindings = _read(inventory), {}
    def visit(item):
        if isinstance(item, dict):
            if "path" in item and "sha256" in item:
                path, digest = item["path"], item["sha256"]
                if path in bindings and bindings[path] != digest:
                    raise ValueError("conflicting input binding")
                bindings[path] = digest
            for child in item.values():
                visit(child)
        elif isinstance(item, list):
            for child in item:
                visit(child)
    visit(value)
    if any(_sha(path) != digest for path, digest in bindings.items()):
        raise ValueError("inventory source binding differs")
    rows = value["proposed_readonly_proof_requests"]
    if len(rows) != 30 or len({row["proof_id"] for row in rows}) != 30:
        raise ValueError("exactly 30 unique proof requests required")
    for row in rows:
        query, endpoint = row["query"], row["endpoint"]
        valid = row["method"] == "GET" and re.fullmatch(r"[A-Za-z0-9_.-]+", row["proof_id"])
        if row["proof_kind"] == "massive_historical_issuer":
            valid = valid and endpoint == "https://api.massive.com/v3/reference/tickers/" + row["expected_symbol"]
            valid = valid and bool(re.fullmatch(r"[A-Z0-9.-]+", row["expected_symbol"])) and set(query) == {"date"}
            valid = valid and date.fromisoformat(query["date"]).isoformat() == query["date"]
        elif row["proof_kind"] == "massive_no_post_cutoff_splits":
            valid = valid and endpoint == "https://api.massive.com/stocks/v1/splits"
            valid = valid and set(query) == {"ticker", "execution_date.gte", "execution_date.lte", "sort", "limit"}
            valid = valid and bool(re.fullmatch(r"[A-Z0-9.-]+", query["ticker"]))
            valid = valid and query["sort"] == "execution_date.asc" and query["limit"] == "1000"
            valid = valid and date.fromisoformat(query["execution_date.gte"]) <= date.fromisoformat(query["execution_date.lte"])
            valid = valid and all(date.fromisoformat(query[k]).isoformat() == query[k]
                                  for k in ("execution_date.gte", "execution_date.lte"))
        else:
            valid = False
        if not valid:
            raise ValueError("request exceeds approved GET whitelist")
    return rows, len(bindings)


def _credential():
    if __package__:
        from scripts.run_minimal_rounds import _load_env
    else:
        from run_minimal_rounds import _load_env
    _load_env()
    value = os.environ.get("MASSIVE_API_KEY", "").strip()
    if not value:
        raise ValueError("MASSIVE_API_KEY unavailable")
    return value


class _NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def collect(inventory, output, max_new_requests, *, opener=None, now=time.time,
            sleep=time.sleep, credential_loader=_credential):
    """Retain bounded raw proofs; failed/interrupted attempts forbid resume."""
    if type(max_new_requests) is not int or not 1 <= max_new_requests <= 30:
        raise ValueError("max-new-requests must be between 1 and 30")
    inventory, output = Path(inventory).resolve(), Path(output).resolve()
    rows, count = _requests(inventory)
    plan = {"inventory": {"path": str(inventory), "sha256": _sha(inventory)},
            "script": {"path": str(Path(__file__).resolve()), "sha256": _sha(__file__)},
            "requests": rows, "max_cumulative_attempts": 30, "requests_per_60_seconds": 5,
            "verified_distinct_nested_bindings": count, "timeout_seconds": 30}
    output.mkdir(exist_ok=True)
    with (output / ".collector.lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        plan_path = output / "plan.json"
        if plan_path.exists():
            if _read(plan_path) != plan:
                raise ValueError("frozen collection plan differs")
        else:
            if any(path.name != ".collector.lock" for path in output.iterdir()):
                raise ValueError("partial output cannot reset collection")
            with plan_path.open("x") as stream:
                json.dump(plan, stream, sort_keys=True, indent=2)
                stream.flush()
                os.fsync(stream.fileno())
        attempts = _read(output / "attempts.json") if (output / "attempts.json").exists() else []
        results = _read(output / "results.json") if (output / "results.json").exists() else []
        by_id = {row["proof_id"]: row for row in rows}
        if (len(attempts) > 30 or len({a["proof_id"] for a in attempts}) != len(attempts)
                or len({r["name"] for r in results}) != len(results)
                or any(type(a["started_epoch"]) not in (int, float)
                       or not math.isfinite(a["started_epoch"]) for a in attempts)):
            raise ValueError("attempt or receipt ledger invalid")
        for receipt in results:
            row = by_id[receipt["name"]]
            if (receipt["endpoint"] != row["endpoint"] or receipt["query"] != row["query"]
                    or receipt["raw_response"] != row["proof_id"] + ".response.json"
                    or _sha(output / receipt["raw_response"]) != receipt["sha256"]
                    or receipt["http_status"] != 200 or receipt["provider_status"] != "OK"
                    or receipt["next_page_present"] is not False):
                raise ValueError("completed receipt binding differs")
            body = _read(output / receipt["raw_response"])
            if (body.get("status") != receipt["provider_status"]
                    or any(k in body and body[k] is not None for k in ("next_url", "next_page", "next_page_token"))
                    or datetime.fromisoformat(receipt["retrieved_at"]).utcoffset() is None):
                raise ValueError("completed response or retrieval instant differs")
        if ({r["name"] for r in results} != {a["proof_id"] for a in attempts}
                or any(a["state"] != "received" or a["proof_id"] not in by_id for a in attempts)):
            raise ValueError("failed or interrupted attempt requires new authorization")
        pending = [row for row in rows if row["proof_id"] not in {r["name"] for r in results}]
        if not pending:
            return {"received": len(results), "pending": 0}
        key = credential_loader()
        opener = opener or build_opener(_NoRedirect())
        for row in pending[:max_new_requests]:
            if len(attempts) >= 30:
                raise ValueError("cumulative attempt ceiling reached")
            if len(attempts) >= 5:
                sleep(max(0, 60.01 - (now() - attempts[-5]["started_epoch"])))
            attempt = {"proof_id": row["proof_id"], "started_epoch": now(), "state": "attempted"}
            attempts.append(attempt)
            atomic_write_json(output / "attempts.json", attempts)
            try:
                request = Request(row["endpoint"] + "?" + urlencode(row["query"]),
                                  headers={"Authorization": "Bearer " + key}, method="GET")
                try:
                    response = opener.open(request, timeout=30)
                except HTTPError as error:
                    response = error
                with response:
                    raw, status = response.read(), response.code
                if key.encode() in raw:
                    raise ValueError("credential appeared in response; body not persisted")
                filename = row["proof_id"] + ".response.json"
                with (output / filename).open("xb") as stream:
                    stream.write(raw)
                body = json.loads(raw)
                receipt = {"name": row["proof_id"], "endpoint": row["endpoint"], "query": row["query"],
                    "retrieved_at": datetime.fromtimestamp(now(), timezone.utc).isoformat(),
                    "http_status": status, "provider_status": body.get("status"),
                    "next_page_present": any(k in body and body[k] is not None for k in ("next_url", "next_page", "next_page_token")),
                    "raw_response": filename, "sha256": hashlib.sha256(raw).hexdigest()}
                results.append(receipt)
                atomic_write_json(output / "results.json", results)
                if status != 200 or receipt["provider_status"] != "OK" or receipt["next_page_present"]:
                    raise ValueError("HTTP/provider/page failure")
                attempt["state"] = "received"
            except Exception as error:
                attempt.update(state="failed", error_type=type(error).__name__)
                atomic_write_json(output / "attempts.json", attempts)
                raise ValueError("proof attempt failed; no retry authorized") from None
            atomic_write_json(output / "attempts.json", attempts)
        return {"received": len(results), "pending": 30 - len(results)}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--inventory", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--max-new-requests", type=int, required=True)
    args = parser.parse_args()
    print(json.dumps(collect(args.inventory, args.output, args.max_new_requests)))
