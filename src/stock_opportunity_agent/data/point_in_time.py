"""Point-in-time filtering and research-packet assembly."""

from __future__ import annotations

from datetime import date, datetime, time, timezone
from typing import Iterable

from stock_opportunity_agent.data.documents import DocumentRecord, documents_to_evidence
from stock_opportunity_agent.models import (
    AsOfContext,
    Catalyst,
    CompanyProfile,
    DataQuality,
    EvidenceItem,
    EvidenceKind,
    FeatureRecord,
    ResearchPacket,
    ValidationError,
    VersionStamp,
)


def utc_day_of_instant(instant: datetime) -> date:
    """Return the UTC daily boundary of an aware instant, rejecting local guesses."""

    if not isinstance(instant, datetime) or instant.tzinfo is None or instant.utcoffset() is None:
        raise ValidationError("daily market cutoff must be an aware datetime")
    return instant.astimezone(timezone.utc).date()


def feature_records_as_of(features: Iterable[FeatureRecord], as_of_date: date) -> list[FeatureRecord]:
    """Return features whose availability date is not after ``as_of_date``."""

    return sorted(
        (feature for feature in features if feature.as_of_date <= as_of_date),
        key=lambda feature: (feature.as_of_date, feature.name, feature.source),
    )


def latest_features_by_name(
    features: Iterable[FeatureRecord],
    as_of_date: date,
    *,
    source_priority: Iterable[str] = (),
) -> dict[str, FeatureRecord]:
    """Select one latest as-of-safe feature per feature name."""

    priority = {source: index for index, source in enumerate(source_priority)}
    selected: dict[str, FeatureRecord] = {}
    for feature in feature_records_as_of(features, as_of_date):
        current = selected.get(feature.name)
        if current is None or _feature_rank(feature, priority) > _feature_rank(current, priority):
            selected[feature.name] = feature
    return selected


def features_to_evidence(features: Iterable[FeatureRecord], as_of_date: date) -> list[EvidenceItem]:
    """Convert normalized features into concise source-linked packet evidence."""

    return [_feature_to_evidence(feature, as_of_date) for feature in features]


def build_research_packet(
    *,
    symbol: str,
    as_of_date: date,
    company: CompanyProfile,
    features: Iterable[FeatureRecord],
    version: VersionStamp,
    documents: Iterable[DocumentRecord] = (),
    catalysts: Iterable[Catalyst] = (),
    theme_ids: Iterable[str] = (),
    memory_refs: Iterable[str] = (),
    packet_id: str | None = None,
    created_at: datetime | None = None,
) -> ResearchPacket:
    """Build a point-in-time ``ResearchPacket`` from normalized data-layer inputs."""

    if not symbol.strip():
        raise ValidationError("symbol must not be empty")
    created = created_at or _default_timestamp(as_of_date)
    selected_features = feature_records_as_of(features, as_of_date)
    if not selected_features:
        selected_features = [
            FeatureRecord(
                name="packet.structured_features",
                value=None,
                as_of_date=as_of_date,
                source="data_layer",
                retrieved_at=created,
                data_quality=DataQuality.MISSING,
                unavailable_reason="no structured features available as of date",
            )
        ]
    selected_documents = [document for document in documents if document.available_as_of(as_of_date)]
    selected_catalysts = catalysts_as_of(catalysts, as_of_date)
    evidence = features_to_evidence(selected_features, as_of_date)
    evidence.extend(documents_to_evidence(selected_documents, as_of_date))
    data_cutoff = _max_retrieved_at(selected_features, selected_documents) or created

    return ResearchPacket(
        packet_id=packet_id or f"{symbol.upper()}:{as_of_date.isoformat()}:research-packet",
        as_of=AsOfContext(as_of_date=as_of_date, data_cutoff=data_cutoff, created_at=created),
        company=company,
        features=selected_features,
        evidence=evidence,
        catalysts=selected_catalysts,
        theme_ids=list(theme_ids),
        memory_refs=list(memory_refs),
        version=version,
    )


def catalysts_as_of(catalysts: Iterable[Catalyst], as_of_date: date) -> list[Catalyst]:
    """Return catalysts whose source evidence was available by ``as_of_date``."""

    selected: list[Catalyst] = []
    for catalyst in catalysts:
        evidence = [
            item
            for item in catalyst.evidence
            if item.as_of_date <= as_of_date and (item.published_date is None or item.published_date <= as_of_date)
        ]
        if not evidence:
            continue
        actual_date = catalyst.actual_date if catalyst.actual_date is not None and catalyst.actual_date <= as_of_date else None
        selected.append(
            Catalyst(
                name=catalyst.name,
                expected_date=catalyst.expected_date,
                status=catalyst.status,
                evidence=evidence,
                actual_date=actual_date,
            )
        )
    return selected


def _feature_to_evidence(feature: FeatureRecord, as_of_date: date) -> EvidenceItem:
    if feature.as_of_date > as_of_date:
        raise ValidationError("feature is not available as of evidence date")
    if feature.data_quality is DataQuality.MISSING:
        return EvidenceItem(
            kind=EvidenceKind.INFERENCE,
            summary=f"{feature.name} unavailable: {feature.unavailable_reason}",
            as_of_date=as_of_date,
            data_quality=DataQuality.MISSING,
            inference=True,
        )

    source_id = feature.source_id or f"{feature.source}:{feature.name}:{feature.as_of_date.isoformat()}"
    return EvidenceItem(
        kind=_evidence_kind_for_feature(feature.name),
        summary=f"{feature.name} = {feature.value}",
        as_of_date=as_of_date,
        source_id=source_id,
        source_url=feature.source_url,
        published_date=feature.as_of_date,
        data_quality=feature.data_quality,
        inference=_feature_is_inference(feature.name),
    )


def _evidence_kind_for_feature(name: str) -> EvidenceKind:
    if name.startswith("price."):
        return EvidenceKind.PRICE_VOLUME
    if name.startswith("financial."):
        return EvidenceKind.FINANCIAL
    if name.startswith("valuation."):
        return EvidenceKind.VALUATION
    if name.startswith("analyst."):
        return EvidenceKind.FINANCIAL
    return EvidenceKind.INFERENCE


def _feature_is_inference(name: str) -> bool:
    return _evidence_kind_for_feature(name) is EvidenceKind.INFERENCE


def _feature_rank(feature: FeatureRecord, priority: dict[str, int]) -> tuple[date, int, int]:
    quality_rank = {
        DataQuality.MISSING: 0,
        DataQuality.STALE: 1,
        DataQuality.ESTIMATED: 2,
        DataQuality.CONFIRMED: 3,
    }[feature.data_quality]
    source_rank = -priority.get(feature.source, len(priority))
    return feature.as_of_date, quality_rank, source_rank


def _max_retrieved_at(
    features: Iterable[FeatureRecord],
    documents: Iterable[DocumentRecord],
) -> datetime | None:
    stamps = [feature.retrieved_at for feature in features]
    stamps.extend(document.retrieved_at for document in documents)
    if not stamps:
        return None
    return max(stamps)


def _default_timestamp(as_of_date: date) -> datetime:
    return datetime.combine(as_of_date, time.min, tzinfo=timezone.utc)
