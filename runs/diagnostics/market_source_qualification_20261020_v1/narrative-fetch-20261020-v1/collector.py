"""Fetch the four predeclared missing SEC URLs once, without modifying caches."""
from pathlib import Path
from datetime import datetime, timezone
from urllib.request import Request, build_opener, HTTPRedirectHandler
from urllib.error import HTTPError
from urllib.parse import urlsplit
import hashlib
import json
import os


ROOT = Path(__file__).resolve().parent
PLAN_SHA = "9bbb1fcc0e49f21424a6ba30ca359ae2c6f3bc779ed0a9443e8b62575d5c512e"


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def main():
    """Retain each attempted request and raw body; never retry an existing run."""
    plan_raw = (ROOT / "request-plan.json").read_bytes()
    assert sha(plan_raw) == PLAN_SHA
    plan = json.loads(plan_raw)
    inventory_raw = Path(plan["narrative_inventory"]["path"]).read_bytes()
    assert sha(inventory_raw) == plan["narrative_inventory"]["sha256"]
    inventory = json.loads(inventory_raw)
    tracked = inventory["input_bindings_after"]
    assert all(sha(Path(row["path"]).read_bytes()) == row["sha256"] for row in tracked)
    result_path = ROOT / "results.json"
    assert not result_path.exists(), "existing attempt inventory cannot be retried"
    user_agent = os.environ.get("SOA_SEC_USER_AGENT", "").strip()
    if not user_agent:
        env_path = Path(plan["source_profile"]["path"]).parents[4] / ".env.local"
        if env_path.is_file():
            for line in env_path.read_text().splitlines():
                if line.startswith("SOA_SEC_USER_AGENT="):
                    user_agent = line.split("=", 1)[1].strip().strip("\"'")
                    break
    if not user_agent:
        user_agent = "stock-opportunity-agent/0.1 contact@example.com"
    headers = {"User-Agent": user_agent, "Accept": "application/json,text/html;q=0.9,*/*;q=0.8", "Accept-Encoding": "identity"}
    opener = build_opener(NoRedirect())
    blocked_hosts = set()
    result = {"plan_sha256": PLAN_SHA, "max_GET_attempts": plan["max_GET_attempts"],
              "GET_attempts": 0, "requests": [], "external_llm_calls": 0,
              "automatic_retries": 0, "redirects_followed": 0, "source_admission": False}

    def save():
        result_path.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n")

    for item in plan["requests"]:
        host = urlsplit(item["url"]).netloc
        if host in blocked_hosts:
            result["requests"].append({"name": item["name"], "url": item["url"],
                "status": "not_attempted_same_host_403_or_429_stop", "GET_attempted": False})
            save()
            continue
        assert result["GET_attempts"] < plan["max_GET_attempts"]
        row = {"name": item["name"], "method": "GET", "url": item["url"],
               "request_headers": headers, "GET_attempted": True,
               "started_at_utc": datetime.now(timezone.utc).isoformat(), "status": "attempt_started"}
        result["GET_attempts"] += 1
        result["requests"].append(row)
        save()
        response = None
        try:
            try:
                response = opener.open(Request(item["url"], headers=headers, method="GET"), timeout=35)
            except HTTPError as exc:
                response = exc
            raw = response.read()
            status = response.code
            row["http_status"] = status
            row["response_url"] = response.geturl()
            row["response_headers"] = {key: ("[REDACTED]" if key.lower() in {"set-cookie", "authorization", "proxy-authorization"} else value)
                                       for key, value in response.headers.items()}
            row["retrieved_at_utc"] = datetime.now(timezone.utc).isoformat()
            raw_path = ROOT / (item["name"] + ".response.raw")
            raw_path.write_bytes(raw)
            row.update(status="http_response_retained", raw_response=str(raw_path), raw_sha256=sha(raw), bytes=len(raw))
            if status in {403, 429}:
                blocked_hosts.add(host)
        except Exception as exc:
            row.update(status="transport_failed", error_type=type(exc).__name__, error=str(exc),
                       finished_at_utc=datetime.now(timezone.utc).isoformat())
        finally:
            if response is not None:
                response.close()
        save()
    result["original_bindings_after"] = [dict(path=row["path"], sha256=sha(Path(row["path"]).read_bytes())) for row in tracked]
    result["originals_unchanged"] = result["original_bindings_after"] == tracked
    assert result["originals_unchanged"]
    result["collector_sha256"] = sha(Path(__file__).read_bytes())
    save()
    print(json.dumps({"result_path": str(result_path), "result_sha256": sha(result_path.read_bytes()),
                      "GET_attempts": result["GET_attempts"],
                      "responses": [{key: value for key, value in row.items() if key in {"name", "status", "http_status", "bytes", "raw_sha256", "error_type"}} for row in result["requests"]]}, indent=2))


if __name__ == "__main__":
    main()
