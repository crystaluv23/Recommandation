"""Synthetic namespace regression; no source, model or research-label access."""
import hashlib
import json
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path

from stock_opportunity_agent.data.raw_info import RawInfoDocument
from stock_opportunity_agent.research.mining_agent_tools import (
    build_same_concept_relations,
    project_facts_from_documents,
)

module = Path("src/stock_opportunity_agent/research/mining_agent_tools.py")
before = hashlib.sha256(module.read_bytes()).hexdigest()
now = datetime(2024, 8, 2, tzinfo=timezone.utc)
body = json.dumps({"facts": {
    "namespace-a": {"Metric": {"units": {"USD": [{"end": "2024-06-30", "val": 120}]}}},
    "namespace-b": {"Metric": {"units": {"USD": [{"end": "2023-06-30", "val": 100}]}}},
}})
document = RawInfoDocument.create(
    document_id="namespace-control-only", company_id="synthetic",
    source_type="company_facts", published_at=now, available_at=now, content=body,
)
facts = project_facts_from_documents((document,), case_ref="synthetic")
relations = build_same_concept_relations(facts)
print(json.dumps({
    "scope": "synthetic namespaces only; no real source changed",
    "module_sha_before": before,
    "module_sha_after": hashlib.sha256(module.read_bytes()).hexdigest(),
    "content": body,
    "facts": [asdict(fact) for fact in facts],
    "relations": [asdict(relation) for relation in relations],
    "expected_automatic_relation_count": 0,
    "namespace_separation_pass": not relations,
}, indent=2, sort_keys=True))
