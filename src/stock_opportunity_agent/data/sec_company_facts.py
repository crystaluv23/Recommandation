"""Pure, issuer-bound SEC Company Facts accession normalization."""
from __future__ import annotations

from collections import Counter
from datetime import date, datetime, time, timedelta, timezone
import hashlib
import json
import re
from typing import Any, Mapping

from stock_opportunity_agent.artifacts import canonical_json_hash as _canonical_hash
from stock_opportunity_agent.data.raw_info import RawInfoDocument
from stock_opportunity_agent.data.sources.core import DataSourceError
from stock_opportunity_agent.models import ValidationError


STANDARD_TAXONOMIES = ("dei", "ifrs-full", "srt", "us-gaap")
STANDARD_FORMS = ("10-K", "10-K/A", "10-Q", "10-Q/A", "20-F", "20-F/A",
                  "40-F", "40-F/A", "6-K", "6-K/A", "8-K", "8-K/A")


def company_fact_available_at(filed: date) -> datetime:
    """Return the conservative policy instant for a date-only filed fact."""
    return datetime.combine(filed + timedelta(days=1), time.min, tzinfo=timezone.utc)


def _source_cik(value: Any) -> str:
    if type(value) is int and 0 < value < 10**10:
        return str(value).zfill(10)
    elif isinstance(value, str) and re.fullmatch(r"[0-9]{1,10}", value.strip()) and int(value.strip()) > 0:
        return value.strip().zfill(10)
    raise DataSourceError("SEC Company Facts CIK shape is invalid")


def validate_company_facts_response(response: Any, expected_cik: str) -> None:
    """Reject a response from another issuer before source construction."""
    if not isinstance(response, Mapping):
        raise DataSourceError("SEC Company Facts response must be an object")
    if _source_cik(response.get("cik")) != _source_cik(expected_cik):
        raise DataSourceError("SEC Company Facts response CIK mismatch")
    if not isinstance(response.get("facts"), Mapping):
        raise DataSourceError("SEC Company Facts response missing facts")


def validate_company_fact_document_issuer(document: RawInfoDocument, payload: Mapping[str, Any]) -> None:
    """Require explicit source-to-company identity for either fact schema."""
    canonical = re.fullmatch(r"cik_([0-9]{10})", document.company_id)
    if canonical:
        expected = canonical.group(1)
        if "cik" in document.metadata and _source_cik(document.metadata["cik"]) != expected:
            raise DataSourceError("SEC Company Facts metadata issuer mismatch")
    elif "cik" in document.metadata:
        expected = _source_cik(document.metadata["cik"])
    else:
        raise DataSourceError("SEC Company Facts opaque company has no explicit issuer binding")
    if _source_cik(payload.get("cik")) != expected:
        raise DataSourceError("SEC Company Facts body issuer mismatch")


def materialize_company_fact_documents(
    response: Mapping[str, Any],
    *,
    item: Mapping[str, Any],
    selection: Mapping[str, Any],
    provenance: Mapping[str, Any],
    retrieved_at: datetime,
) -> tuple[list[RawInfoDocument], dict[str, Any]]:
    """Build existing typed accession documents under an explicit selection."""
    cik = str(item["cik"])
    validate_company_facts_response(response, cik)
    if set(provenance) - {"backfill_plan_hash", "acquisition_policy_hash", "acquisition_selection"}:
        raise ValidationError("unsupported Company Facts provenance field")
    _parse_datetime(retrieved_at.isoformat(), "Company Facts retrieval time")
    company_id = str(item["company_id"])
    symbol = str(item.get("symbol") or "")
    source_url = str(item["source_url"])
    if company_id.startswith("cik_") and company_id != "cik_" + cik:
        raise DataSourceError("SEC Company Facts company identity mismatch")
    period_end_from = _parse_date(
        selection.get("period_end_from"), "fact period_end_from"
    )
    period_end_through = _parse_date(
        selection.get("period_end_through"), "fact period_end_through"
    )
    available_at_through = _parse_datetime(
        selection.get("available_at_through"), "fact available_at_through"
    )
    allowed_taxonomies = set(selection.get("taxonomy_allowlist", ()))
    allowed_forms = set(selection.get("form_allowlist", ()))
    facts = response.get("facts")
    if not isinstance(facts, Mapping):
        raise DataSourceError("SEC Company Facts response missing facts")
    excluded: Counter[str] = Counter()
    raw_fact_rows = 0
    groups: dict[str, dict[str, Any]] = {}
    for raw_taxonomy, raw_concepts in facts.items():
        taxonomy = str(raw_taxonomy)
        if not isinstance(raw_concepts, Mapping):
            excluded["invalid_taxonomy_payload"] += 1
            continue
        if taxonomy not in allowed_taxonomies:
            skipped = _count_company_fact_rows(raw_concepts)
            raw_fact_rows += skipped
            excluded["taxonomy_not_allowed"] += skipped
            continue
        for raw_tag, raw_concept in raw_concepts.items():
            tag = str(raw_tag)
            if not isinstance(raw_concept, Mapping):
                excluded["invalid_concept_payload"] += 1
                continue
            label = str(raw_concept.get("label") or "").strip() or None
            description = (
                str(raw_concept.get("description") or "").strip() or None
            )
            units = raw_concept.get("units")
            if not isinstance(units, Mapping):
                excluded["missing_units"] += 1
                continue
            for raw_unit, raw_rows in units.items():
                unit = str(raw_unit)
                if not isinstance(raw_rows, list):
                    excluded["invalid_unit_rows"] += 1
                    continue
                for raw_row in raw_rows:
                    raw_fact_rows += 1
                    if not isinstance(raw_row, Mapping):
                        excluded["invalid_fact_row"] += 1
                        continue
                    accession = str(raw_row.get("accn") or "")
                    if not re.fullmatch(r"\d{10}-\d{2}-\d{6}", accession):
                        excluded["invalid_accession"] += 1
                        continue
                    form = str(raw_row.get("form") or "").strip().upper()
                    if form not in allowed_forms:
                        excluded["form_not_allowed"] += 1
                        continue
                    filed_date = _optional_fact_date(raw_row.get("filed"))
                    if filed_date is None:
                        excluded["invalid_filed_date"] += 1
                        continue
                    available_at = company_fact_available_at(filed_date)
                    if available_at > available_at_through:
                        excluded["unavailable_by_latest_cutoff"] += 1
                        continue
                    end_date = _optional_fact_date(raw_row.get("end"))
                    if end_date is None:
                        excluded["invalid_period_end"] += 1
                        continue
                    if end_date < period_end_from:
                        excluded["period_before_lookback"] += 1
                        continue
                    if end_date > period_end_through:
                        excluded["period_after_latest_cutoff"] += 1
                        continue
                    start_date: date | None = None
                    if raw_row.get("start") is not None:
                        start_date = _optional_fact_date(raw_row.get("start"))
                        if start_date is None or start_date > end_date:
                            excluded["invalid_period_start"] += 1
                            continue
                    value = raw_row.get("val")
                    if isinstance(value, bool) or not isinstance(
                        value, (int, float, str)
                    ):
                        excluded["invalid_fact_value"] += 1
                        continue
                    fact = {
                        "taxonomy": taxonomy,
                        "tag": tag,
                        "label": label,
                        "description": description,
                        "unit": unit,
                        "value": value,
                        "start": start_date.isoformat() if start_date else None,
                        "end": end_date.isoformat(),
                        "fiscal_year": raw_row.get("fy"),
                        "fiscal_period": raw_row.get("fp"),
                        "frame": raw_row.get("frame"),
                    }
                    fact_key = _canonical_hash(fact)
                    group = groups.setdefault(
                        accession,
                        {
                            "filing_date": filed_date,
                            "form": form,
                            "available_at": available_at,
                            "facts": {},
                        },
                    )
                    if group["filing_date"] != filed_date or group["form"] != form:
                        raise DataSourceError(
                            f"conflicting SEC Company Facts filing metadata: {accession}"
                        )
                    group["facts"][fact_key] = fact
    documents: list[RawInfoDocument] = []
    selected_fact_rows = 0
    for accession, group in sorted(groups.items()):
        selected_facts = sorted(
            group["facts"].values(),
            key=lambda fact: (
                fact["taxonomy"],
                fact["tag"],
                fact["unit"],
                fact["end"],
                fact["start"] or "",
                json.dumps(fact["value"], sort_keys=True),
            ),
        )
        if not selected_facts:
            continue
        selected_fact_rows += len(selected_facts)
        content_payload = {
            "schema_version": "sec-company-facts-document-v1",
            "cik": cik,
            "accession_number": accession,
            "filing_date": group["filing_date"].isoformat(),
            "form": group["form"],
            "facts": selected_facts,
        }
        content = json.dumps(
            content_payload,
            sort_keys=True,
            separators=(",", ":"),
        )
        version_hash = hashlib.sha256(content.encode("utf-8")).hexdigest()
        documents.append(
            RawInfoDocument.create(
                document_id=(
                    f"secfacts:{cik}:{accession}:{version_hash[:16]}"
                ),
                company_id=company_id,
                source_type="sec_company_facts",
                published_at=_midnight_utc(group["filing_date"]),
                available_at=group["available_at"],
                content=content,
                metadata={
                    **({"symbol": symbol} if symbol else {}),
                    "cik": cik,
                    "accession_number": accession,
                    "form": group["form"],
                    "source_key": "sec_edgar",
                    "source_url": source_url,
                    "retrieved_at": retrieved_at.isoformat(),
                    **dict(provenance),
                    "content_scope": "standard_taxonomy_facts_for_accession",
                    "fact_count": len(selected_facts),
                    "taxonomy_namespaces": sorted(
                        {fact["taxonomy"] for fact in selected_facts}
                    ),
                    "period_end_from": period_end_from.isoformat(),
                    "period_end_through": period_end_through.isoformat(),
                    "availability_policy": (
                        "next_utc_day_after_companyfacts_filed_date"
                    ),
                    "retrospective_api_extraction": True,
                    "requires_primary_filing_audit": True,
                },
            )
        )
    return documents, {
        "raw_fact_row_count": raw_fact_rows,
        "selected_fact_row_count": selected_fact_rows,
        "excluded_reason_counts": dict(sorted(excluded.items())),
    }


def _count_company_fact_rows(concepts: Mapping[str, Any]) -> int:
    count = 0
    for concept in concepts.values():
        units = concept.get("units") if isinstance(concept, Mapping) else None
        if not isinstance(units, Mapping):
            continue
        count += sum(len(rows) for rows in units.values() if isinstance(rows, list))
    return count


def _optional_fact_date(value: Any) -> date | None:
    if not value:
        return None
    try:
        return date.fromisoformat(str(value))
    except ValueError:
        return None


def _parse_date(value: Any, name: str) -> date:
    if not value:
        raise ValidationError(f"missing {name}")
    try:
        return date.fromisoformat(str(value))
    except ValueError as exc:
        raise ValidationError(f"invalid {name}") from exc


def _parse_datetime(value: Any, name: str) -> datetime:
    if not value:
        raise ValidationError(f"missing {name}")
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValidationError(f"invalid {name}") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValidationError(f"{name} must be timezone-aware")
    return parsed.astimezone(timezone.utc)


def _midnight_utc(value: date) -> datetime:
    return datetime.combine(value, time.min, tzinfo=timezone.utc)

