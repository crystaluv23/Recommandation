"""Retain current MS root and its uniquely date-matched archive page once."""
from pathlib import Path
from datetime import datetime, timezone
from urllib.request import Request, build_opener, HTTPRedirectHandler
from urllib.error import HTTPError
import hashlib
import json
import re


ROOT = Path(__file__).resolve().parent
PLAN_SHA = "6c64e6713f3b4cf18a002fd35a9a3120261e2d38d56462bab635c050d793b2e1"


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def main():
    """Fetch no more than two planned URLs; ambiguous current linkage stops."""
    raw_plan = (ROOT / "request-plan.json").read_bytes()
    assert digest(raw_plan) == PLAN_SHA
    plan = json.loads(raw_plan)
    previous = Path(plan["prior_terminal_results"]["path"])
    assert digest(previous.read_bytes()) == plan["prior_terminal_results"]["sha256"]
    old_root = previous.parent
    old_hashes = {str(p): digest(p.read_bytes()) for p in old_root.rglob("*") if p.is_file()}
    headers = json.loads(previous.read_bytes())["requests"][0]["request_headers"]
    opener = build_opener(NoRedirect())
    output = ROOT / "results.json"
    assert not output.exists(), "existing GET attempts cannot be retried"
    result = {"plan_sha256": PLAN_SHA, "max_GET_attempts": 2, "GET_attempts": 0,
              "requests": [], "external_llm_calls": 0, "automatic_retries": 0,
              "redirects_followed": 0, "source_admission": False}

    def save():
        output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n")

    def fetch(name, url):
        assert result["GET_attempts"] < 2
        row = {"name": name, "method": "GET", "url": url, "request_headers": headers,
               "started_at_utc": datetime.now(timezone.utc).isoformat(), "status": "attempt_started"}
        result["GET_attempts"] += 1
        result["requests"].append(row)
        save()
        response = None
        try:
            try:
                response = opener.open(Request(url, headers=headers, method="GET"), timeout=35)
            except HTTPError as exc:
                response = exc
            raw = response.read()
            path = ROOT / (name + ".response.raw")
            path.write_bytes(raw)
            row.update(status="http_response_retained", http_status=response.code,
                       response_url=response.geturl(), retrieved_at_utc=datetime.now(timezone.utc).isoformat(),
                       raw_response=str(path), raw_sha256=digest(raw), bytes=len(raw))
            row["response_headers"] = {key: ("[REDACTED]" if key.lower() in {"set-cookie", "authorization", "proxy-authorization"} else value)
                                       for key, value in response.headers.items()}
            save()
            return json.loads(raw) if response.code == 200 else None
        except Exception as exc:
            row.update(status="transport_or_JSON_failed", error_type=type(exc).__name__, error=str(exc))
            save()
            return None
        finally:
            if response is not None:
                response.close()

    current = fetch("ms_current_submissions_root", plan["first_request"]["url"])
    if current is not None:
        target = plan["second_request_selection"]["target_filing_date"]
        matches = [entry for entry in current.get("filings", {}).get("files", [])
                   if entry.get("filingFrom", "~") <= target <= entry.get("filingTo", "")]
        if (str(current.get("cik")).zfill(10) == "0000895421" and len(matches) == 1
                and re.fullmatch(r"CIK0000895421-submissions-[0-9]+\.json", matches[0].get("name", ""))):
            selected = {"root_sha256": result["requests"][0]["raw_sha256"], "root_file_entry": matches[0],
                        "method": "GET", "url": "https://data.sec.gov/submissions/" + matches[0]["name"]}
            (ROOT / "selected-second-request.json").write_text(json.dumps(selected, indent=2) + "\n")
            result["selected_second_request"] = selected
            fetch("ms_linked_submissions_archive", selected["url"])
        else:
            result["second_request_not_attempted"] = {"reason": "missing/ambiguous or foreign issuer archive linkage", "matching_entries": matches}
    old_after = {str(p): digest(p.read_bytes()) for p in old_root.rglob("*") if p.is_file()}
    result["old_four_request_files_before"] = old_hashes
    result["old_four_request_files_after"] = old_after
    result["old_four_request_files_unchanged"] = old_after == old_hashes
    assert result["old_four_request_files_unchanged"]
    result["collector_sha256"] = digest(Path(__file__).read_bytes())
    save()
    print(json.dumps({"result_path": str(output), "sha256": digest(output.read_bytes()),
                      "GET_attempts": result["GET_attempts"],
                      "responses": [{key: value for key, value in row.items() if key in {"name", "url", "status", "http_status", "bytes", "raw_sha256", "error_type"}} for row in result["requests"]]}, indent=2))


if __name__ == "__main__":
    main()
