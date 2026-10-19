"""Exercise the driver gate with native replay in a temporary source store."""
import hashlib
import json
from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path
import tempfile

from stock_opportunity_agent.artifacts import atomic_write_json
from stock_opportunity_agent.data.raw_info import RawInfoDocument, RawInfoStore
from stock_opportunity_agent.data.reviewed_snapshot import ReviewedSourceRejected
import diagnose_reviewed_anchor_financial_snapshot as driver


def run():
    """Use only explicit synthetic records and temporary on-disk native stores."""
    script = Path(driver.__file__).resolve()
    before = hashlib.sha256(script.read_bytes()).hexdigest()
    source = RawInfoDocument.create(document_id="replay-gate", company_id="issuer",
        source_type="sec_company_facts", published_at=datetime(2025, 7, 31, tzinfo=timezone.utc),
        available_at=datetime(2025, 7, 31, tzinfo=timezone.utc), content='{"synthetic":true}',
        metadata={"test_only": True, "value": True})
    cases = []
    with tempfile.TemporaryDirectory() as temporary:
        root = Path(temporary)
        store = RawInfoStore(root=root, documents=(source,))
        originals = {str(p.relative_to(root)): hashlib.sha256(p.read_bytes()).hexdigest()
                     for p in root.rglob("*.json")}
        for name, candidate, rejected in (
            ("exact", replace(source), False),
            ("boolean_to_integer", replace(source, metadata={"test_only": True, "value": 1}), True),
            ("boolean_to_float", replace(source, metadata={"test_only": True, "value": 1.0}), True),
            ("only_clock", replace(source, available_at=datetime(2025, 8, 1, tzinfo=timezone.utc)), True),
        ):
            replay = store.append(candidate)
            canonical = store.load(source.document_id)
            try:
                driver._require_same_record(canonical, candidate)
            except ReviewedSourceRejected:
                actual_rejected = True
            else:
                actual_rejected = False
            assert replay is False
            assert actual_rejected is rejected
            assert driver._same_document_set((canonical,), (candidate,)) is (not rejected)
            assert {str(p.relative_to(root)): hashlib.sha256(p.read_bytes()).hexdigest()
                    for p in root.rglob("*.json")} == originals
            cases.append({"case": name, "native_append_returned": replay,
                "python_record_equality": canonical.to_dict() == candidate.to_dict(),
                "driver_gate_rejected": actual_rejected,
                "worker_restore_collection_equal": driver._same_document_set((canonical,), (candidate,)),
                "stored_bytes_unchanged": True})
        restored = RawInfoStore(root=root)
        driver._require_same_record(restored.load(source.document_id), source)
    after = hashlib.sha256(script.read_bytes()).hexdigest()
    assert before == after
    return {"status": "passed", "script": {"path": str(script), "sha256": after},
        "cases": cases, "fresh_temp_restart_exact": True,
        "real_global_oracle_opened": False, "diagnostic_prepare_or_execute_called": False,
        "network_requests": 0, "models": 0, "labels_loaded": False}


if __name__ == "__main__":
    result = run()
    atomic_write_json(Path(__file__).with_name("canonical-replay-gate-result.json"), result)
    print(json.dumps(result, indent=2))
