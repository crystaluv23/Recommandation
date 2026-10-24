"""Read original Registry bytes and independently capture repair input authority.

No Registry constructor, staging, admission, promotion, or acquisition is used.
Outputs are confined to this script's diagnostic directory.
"""
from pathlib import Path
import hashlib
import json

from stock_opportunity_agent.signal_library import SignalRegistry, _audit_deterministic_fixture


ROOT = Path(__file__).resolve().parents[4]
ORIGINAL = ROOT / "runs/cold_start/minimal_rounds_v182_integrated/signals"
OUT = Path(__file__).resolve().parent


def content_manifest():
    return {str(path.relative_to(ORIGINAL)): hashlib.sha256(path.read_bytes()).hexdigest()
            for path in sorted(ORIGINAL.rglob("*")) if path.is_file()}


def main():
    before = content_manifest()
    registry = object.__new__(SignalRegistry)
    registry.root = ORIGINAL
    registry.knowledge_workspace_root = ORIGINAL.parent
    registry.candidate_root = OUT / "unused_candidates"
    registry._transition_recovery_active = False
    registry._fault_injector = None
    cards = registry.list_signal_cards()
    refs = tuple(card.ref for card in cards)
    snapshot = registry.snapshot_from_refs(registry.version, refs)
    audit = registry.audit_capabilities().to_dict()
    details = {}
    for ref in audit["disabled"]:
        spec = registry.load_spec(ref)
        tests = registry.load_tests(ref)
        fixture_details = []
        for index, fixture in enumerate(tests):
            try:
                _audit_deterministic_fixture(spec, fixture, index=index)
                reason = None
            except Exception as exc:
                reason = f"{type(exc).__name__}: {exc}"
            docs = []
            for doc in fixture.get("documents", ()):
                try:
                    body = json.loads(doc["content"])
                except (json.JSONDecodeError, TypeError):
                    body = {}
                docs.append({"document_id": doc.get("document_id"),
                             "source_type": doc.get("source_type"),
                             "body_cik": body.get("cik") if isinstance(body, dict) else None,
                             "metadata_cik": doc.get("metadata", {}).get("cik"),
                             "body_keys": sorted(body) if isinstance(body, dict) else [],
                             "reported_windows": [{key: fact.get(key) for key in ("tag", "start", "end", "fy", "fp", "frame", "unit")}
                                                  for fact in body.get("facts", ()) if isinstance(fact, dict)]
                             if isinstance(body, dict) and isinstance(body.get("facts"), list) else []})
            fixture_details.append({"name": fixture.get("name"), "expected": fixture.get("expected"),
                                    "failure": reason, "documents": docs})
        details[ref] = {"next_ref": f"{spec.signal_id}:v{spec.version + 1}",
                        "fixture_count": len(tests), "fixtures": fixture_details}
    try:
        registry.freeze()
        freeze_failure = None
    except Exception as exc:
        freeze_failure = f"{type(exc).__name__}: {exc}"
    after = content_manifest()
    assert before == after, "original registry changed during read-only capture"
    result = {"schema_version": "independent-capability-repair-baseline-v1",
              "original_root": str(ORIGINAL), "original_file_count": len(before),
              "original_files": before,
              "original_manifest_hash": hashlib.sha256(json.dumps(before, sort_keys=True, separators=(",", ":")).encode()).hexdigest(),
              "registry_version": registry.version, "registry_definition_hash": snapshot.registry_hash,
              "ordered_refs": list(refs), "audit": audit,
              "disabled_fixture_details": details,
              "ordinary_freeze_failure": freeze_failure, "original_unchanged": before == after,
              "claim": "Read-only baseline evidence; no repair implemented, admitted or published."}
    (OUT / "baseline.json").write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps({k: result[k] for k in ("original_file_count", "original_manifest_hash", "registry_version", "registry_definition_hash", "ordered_refs", "audit", "original_unchanged")}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
