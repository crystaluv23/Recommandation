"""Fixed synthetic read-ranking counterexamples; never execute a Signal."""
import hashlib
import json
import re
from datetime import datetime, timezone
from pathlib import Path

from stock_opportunity_agent.data.raw_info import RawInfoDocument
from stock_opportunity_agent.data.resolution import (
    RawInfoRequest, _rank_documents, _select_required_source_documents,
    _retrieval_contract_coverage,
)
from stock_opportunity_agent.research.evolution_settings import _LLM_SIGNAL_QUERY_STOP_WORDS

OUT = Path(__file__).resolve().parent
QUERY = "cash current liabilities"
TERMS = {t.casefold() for t in re.findall(r"[A-Za-z0-9]+", QUERY)
         if len(t) >= 3 and t.casefold() not in _LLM_SIGNAL_QUERY_STOP_WORDS}


def document(identifier, public_day, *, end="2025-03-31", unit="USD", repetitions=3,
             role="irrelevant training example", schema="synthetic-row-list"):
    """Create explicitly synthetic content, not source-qualified or measured data."""
    content = json.dumps({"schema": schema, "description": (QUERY + " ") * repetitions,
                          "tag": role, "unit": unit, "end": end, "value": 110},
                         separators=(",", ":"))
    instant = datetime.fromisoformat(public_day).replace(tzinfo=timezone.utc)
    return RawInfoDocument.create(document_id=identifier, company_id="synthetic-issuer",
                                  source_type="filing", published_at=instant,
                                  available_at=instant, content=content)


def candidate_key(doc):
    """Diagnostic analogue of existing projection lexical scoring; not installed."""
    tokens = re.findall(r"[A-Za-z0-9]+", doc.content.casefold())
    return (-len(TERMS.intersection(tokens)),
            -sum(min(tokens.count(term), 3) for term in TERMS),
            -doc.available_at.timestamp(), doc.document_id)


def selection(pool, needed, *, periods=None):
    """Use the real required selector over both existing and candidate ordering."""
    request = RawInfoRequest(request_id="diagnostic", description="Synthetic query-only read",
                            source_types=("filing",), max_documents=10, query=QUERY,
                            required_source_groups=(("filing",),), minimum_distinct_periods=periods)
    results = {}
    for name, ranked in (("native_substring", _rank_documents(pool, request)),
                         ("projection_style_candidate", sorted(pool, key=candidate_key))):
        chosen = _select_required_source_documents(ranked, request)
        ids = [doc.document_id for doc in chosen]
        assert len(ids) <= 10 and len(set(ids)) == len(ids)
        results[name] = {"selected": ids, "missing_semantically_needed": sorted(set(needed) - set(ids)),
                         "coverage": _retrieval_contract_coverage(chosen, request)}
    return results


latest = document("latest-real-facts", "2025-05-30", role="cash/current-liabilities intended operands")
repetition = [document(f"old-word-pump-{i}", "2025-02-01", repetitions=100,
                       role=f"unrelated boilerplate {i}") for i in range(10)]
essential = [latest,
             document("necessary-conflict", "2025-05-20", role="same-period conflicting amount"),
             document("necessary-comparable", "2025-02-15", end="2024-03-31", role="same-duration prior"),
             document("necessary-currency-witness", "2025-02-10", unit="CAD", role="currency reconciliation basis")]
noise = [document(f"irrelevant-new-{i}", "2025-05-25", end="2024-12-31",
                  role=f"ShareBasedCompensation unrelated disclosure {i}") for i in range(8)]
new_irrelevant = document("irrelevant-extra", "2025-05-31", end="2024-12-31", role="unrelated training text")
currency_pool = [document(f"a-unit-{i}", "2025-05-30", unit=unit, role="cash/current-liabilities operands")
                 for i, unit in enumerate(("CAD", "EUR", "GBP", "JPY", "AUD", "CHF", "CNY", "INR", "BRL", "MXN"))]
currency_pool.append(document("z-unit-USD", "2025-05-30", role="cash/current-liabilities operands"))
legacy = document("legacy-readable", "2025-02-15", schema="synthetic-nested", role="skill-supported source format")
new_format = [document(f"new-format-{i}", "2025-05-30", role=f"skill-unsupported typed list {i}") for i in range(10)]
pools = {"word_repetition": [latest, *repetition],
         "essential_old_witnesses": [*essential, *noise],
         "one_extra_irrelevant": [*essential, *noise, new_irrelevant],
         "query_underdetermines_currency": currency_pool,
         "version_skill_format": [legacy, *new_format]}
original = {key: [doc.to_dict() for doc in pool] for key, pool in pools.items()}
results = {
    "word_repetition": selection(pools["word_repetition"], {latest.document_id}),
    "essential_old_witnesses": selection(pools["essential_old_witnesses"], {d.document_id for d in essential}, periods=2),
    "one_extra_irrelevant": selection(pools["one_extra_irrelevant"], {d.document_id for d in essential}, periods=2),
    "query_underdetermines_currency": selection(currency_pool, {"z-unit-USD"}),
    "version_skill_format": selection([legacy, *new_format], {legacy.document_id}),
}
assert results["word_repetition"]["native_substring"]["missing_semantically_needed"] == ["latest-real-facts"]
assert not results["word_repetition"]["projection_style_candidate"]["missing_semantically_needed"]
base = results["essential_old_witnesses"]["projection_style_candidate"]
added = results["one_extra_irrelevant"]["projection_style_candidate"]
assert base["coverage"]["contract_satisfied"] and added["coverage"]["contract_satisfied"]
assert "necessary-conflict" not in base["missing_semantically_needed"]
assert "necessary-conflict" in added["missing_semantically_needed"]
assert {"necessary-comparable", "necessary-currency-witness"} <= set(base["missing_semantically_needed"])
assert results["query_underdetermines_currency"]["projection_style_candidate"]["missing_semantically_needed"] == ["z-unit-USD"]
assert results["version_skill_format"]["projection_style_candidate"]["missing_semantically_needed"] == ["legacy-readable"]
assert original == {key: [doc.to_dict() for doc in pool] for key, pool in pools.items()}
(OUT / "fixed-pools.json").write_text(json.dumps(original, indent=2) + "\n")
output = {"scope": "synthetic pure ranking/real required-selector only, no service or model execution",
          "query": QUERY, "results": results, "raw_records_unchanged": True,
          "interpretation": "Projection-style lexical ranking reduces repetition bias but cannot identify arbitrary tag/unit/period/conflict/skill-format witnesses from a query-only contract; required source/period counts can be satisfied by irrelevant periods."}
(OUT / "probe-results.json").write_text(json.dumps(output, indent=2) + "\n")
print(json.dumps({key: value["projection_style_candidate"]["missing_semantically_needed"] for key, value in results.items()}))
