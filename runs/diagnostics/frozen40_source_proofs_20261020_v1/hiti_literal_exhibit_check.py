"""Check two literal HITI parent-exhibit links and bounded exact cache paths."""
import json
from pathlib import Path
from urllib.parse import urljoin

from fti_market_window_check import bound, ROOT, PARENT
from stock_opportunity_agent.artifacts import atomic_write_json
from stock_opportunity_agent.data.reviewed_snapshot import _SecExhibitLinks, _proved_sec_exhibit_code
from stock_opportunity_agent.data.sources.catalog import DataCapability
from stock_opportunity_agent.data.sources.state import RawCacheKey


def main():
    """Preserve parent index/prose conflict without fetching or qualifying exhibits."""
    output = PARENT / "hiti-literal-exhibit-local-check.json"
    assert not output.exists(), "Existing check is terminal."
    report_path = PARENT / "operating-content-review.json"
    report_binding = bound(report_path)
    assert report_binding["sha256"] == "15da9a9f261910663a2502a58c9b20a7a85fb8a97e0ca7acb5dd2f1b7b7617e4"
    report = json.loads(report_path.read_bytes())
    row = next(t for t in report["targets"] if t["ticker"] == "HITI")
    parent = row["parent_exhibit_link_candidates"]
    original_binding = parent["parent_original_bindings"][0]
    assert bound(original_binding["path"]) == original_binding
    document = json.loads(Path(original_binding["path"]).read_bytes())
    assert document["company_id"] == parent["parent_company_id"] == "cik_0001847409"
    parser = _SecExhibitLinks(); parser.feed(document["content"])
    inventory_path = ROOT / "runs/diagnostics/frozen40_source_completion_20261020_v1/local-cache-chain-inventory.json"
    inventory_binding = bound(inventory_path)
    assert inventory_binding["sha256"] == "5bf5a7bbe1c86ef8ca58b7270695eb32b846f64ce306fedaf42f3ed88f1eeb9a"
    inventory = json.loads(inventory_path.read_bytes())
    directories = sorted({str(Path(b["path"]).parent) for b in inventory["read_file_bindings"]
        if "/cache/data/sec_edgar/filing_documents/" in b["path"]})
    results = []
    for link in parent["links"]:
        endpoint = urljoin(parent["parent_source_url"], link["literal_href"])
        assert endpoint == link["resolved_url"] and link["literal_href"] in parser.links
        assert _proved_sec_exhibit_code(parser, parent["parent_source_url"], endpoint, link["number_cell"])
        key = RawCacheKey.from_request("sec_edgar", DataCapability.FILING_DOCUMENTS, "GET", endpoint)
        probes = [str(Path(directory) / (key.digest + ".json")) for directory in directories]
        matches = [bound(path) for path in probes if Path(path).is_file()]
        for binding in matches:
            cache = json.loads(Path(binding["path"]).read_bytes())
            assert cache["endpoint"] == endpoint and cache["params"] == [["method", "GET"]]
        results.append({"method": "GET", "endpoint": endpoint, "query": {},
            "document_role": "incorporated_exhibit", "description_role": link["description_role"],
            "literal_href": link["literal_href"], "proved_index_code": link["number_cell"],
            "parent_company_id": parent["parent_company_id"], "parent_cik": parent["parent_cik"],
            "parent_form": parent["parent_form"], "parent_accession": parent["parent_accession"],
            "parent_url": parent["parent_source_url"], "parent_accepted_at": parent["parent_accepted_at"],
            "parent_original": original_binding, "parent_root_proofs": [v["root"] for v in row["stage_body_variants"]],
            "cache_key": key.digest, "direct_paths_checked": probes, "matches": matches,
            "future_body_content_review_required": True})
    atomic_write_json(output, {"scope": "Two literal source-bound parent exhibits, not new admission or guessed link discovery.",
        "inputs": [report_binding, original_binding, inventory_binding],
        "native_verifier": bound(ROOT / "src/stock_opportunity_agent/data/reviewed_snapshot.py"),
        "cache_directories_checked": directories, "requests": results,
        "parent_prose_index_conflict": parent["prose_index_number_conflict"],
        "no_conflict_rewritten": True, "network_requests": 0, "global_store_or_append": False})
    print(json.dumps({"exact_link_count": len(results), "cache_directories": len(directories),
        "exact_matches": sum(len(r["matches"]) for r in results), "output": bound(output)}))


if __name__ == "__main__":
    main()
