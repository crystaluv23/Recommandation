"""Historical case packet construction helpers."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from typing import Iterable, Mapping

from stock_opportunity_agent.cases.learning import HistoricalCase
from stock_opportunity_agent.cases.outcomes import OutcomeDefinition, label_price_outcome
from stock_opportunity_agent.data.documents import DocumentRecord
from stock_opportunity_agent.data.point_in_time import build_research_packet, latest_features_by_name
from stock_opportunity_agent.data.sources.core import PriceBar, SecurityListing
from stock_opportunity_agent.data.structured import company_profile_from_features
from stock_opportunity_agent.models import Catalyst, FeatureRecord, VersionStamp


@dataclass(frozen=True)
class CaseSlicePlan:
    """As-of offsets used before an outcome window starts."""

    offsets_days: tuple[int, ...] = (180, 120, 90, 60, 30)

    def as_of_dates(self, outcome_start_date: date) -> tuple[date, ...]:
        """Return sorted as-of dates before the outcome start."""

        return tuple(sorted(outcome_start_date - timedelta(days=days) for days in self.offsets_days))


def build_historical_cases_from_packets(
    *,
    listings: Iterable[SecurityListing],
    bars_by_symbol: Mapping[str, Iterable[PriceBar]],
    features_by_symbol: Mapping[str, Iterable[FeatureRecord]],
    version: VersionStamp,
    outcome_definition: OutcomeDefinition,
    slice_plan: CaseSlicePlan | None = None,
    inflection_dates_by_symbol: Mapping[str, date] | None = None,
    documents_by_symbol: Mapping[str, Iterable[DocumentRecord]] | None = None,
    catalysts_by_symbol: Mapping[str, Iterable[Catalyst]] | None = None,
) -> tuple[HistoricalCase, ...]:
    """Build labeled historical cases from data-layer records.

    This is the executable bridge between the data layer and cold-start
    learning. It labels retrospective outcomes from future bars, but each
    `ResearchPacket` is assembled only from data available on its as-of date.
    """

    plan = slice_plan or CaseSlicePlan()
    inflection_dates = {symbol.upper(): value for symbol, value in (inflection_dates_by_symbol or {}).items()}
    documents = documents_by_symbol or {}
    catalysts = catalysts_by_symbol or {}
    cases: list[HistoricalCase] = []
    for listing in listings:
        symbol = listing.symbol.upper()
        bars = list(bars_by_symbol.get(symbol, ()))
        if not bars:
            continue
        anchor_date = inflection_dates.get(symbol)
        if anchor_date is None:
            continue
        try:
            label, observation = label_price_outcome(symbol, bars, anchor_date, outcome_definition)
        except Exception:
            continue
        if label.value == "unlabeled":
            continue
        for as_of_date in plan.as_of_dates(anchor_date):
            if as_of_date >= anchor_date:
                continue
            if label.value == "unlabeled":
                continue
            features = list(latest_features_by_name(features_by_symbol.get(symbol, ()), as_of_date).values())
            company = company_profile_from_features(listing, features, as_of_date)
            packet = build_research_packet(
                symbol=symbol,
                as_of_date=as_of_date,
                company=company,
                features=features,
                version=version,
                documents=documents.get(symbol, ()),
                catalysts=catalysts.get(symbol, ()),
                theme_ids=[],
                packet_id=f"{symbol}:{as_of_date.isoformat()}:historical-case",
            )
            cases.append(
                HistoricalCase(
                    case_id=f"{symbol}:{as_of_date.isoformat()}:{label.value}",
                    label=label,
                    packet=packet,
                    outcome_start_date=observation.outcome_start_date,
                    outcome_end_date=observation.outcome_end_date,
                    outcome_return=observation.forward_return,
                    matched_group_id=f"unmatched:{symbol}:{as_of_date.isoformat()}",
                    hidden_outcome_summary=(
                        "Outcome label and forward return are retrospective metadata hidden from packet evidence."
                    ),
                    outcome_definition_id=outcome_definition.definition_id,
                )
            )
    return tuple(cases)
