"""SEC EDGAR data-source provider."""

from __future__ import annotations

from datetime import date
from typing import Any

from stock_opportunity_agent.config import DataSourceConfig
from stock_opportunity_agent.data.sources import register
from stock_opportunity_agent.data.sources.core import (
    DataSourceError,
    FilingMetadata,
    JsonTransport,
    array_get,
    format_cik,
    optional_date,
    utc_now,
)
from stock_opportunity_agent.models import ValidationError


class SecEdgarClient:
    """SEC EDGAR submissions and company facts client."""

    def __init__(
        self,
        user_agent: str,
        *,
        base_url: str = "https://data.sec.gov",
        transport: JsonTransport | None = None,
    ) -> None:
        if not user_agent.strip():
            raise ValidationError("SEC user_agent must not be empty")
        from stock_opportunity_agent.data.sources.core import UrllibJsonTransport

        self.user_agent = user_agent
        self.base_url = base_url.rstrip("/")
        self.transport = transport or UrllibJsonTransport()

    @classmethod
    def from_config(cls, config: DataSourceConfig, transport: JsonTransport | None = None) -> "SecEdgarClient":
        """Create an EDGAR client from data-source config."""

        return cls(config.sec_user_agent, transport=transport)

    def submissions(self, cik: str) -> dict[str, Any]:
        """Return raw SEC submissions JSON for a zero-padded CIK."""

        return self.transport.get_json(
            f"{self.base_url}/submissions/CIK{format_cik(cik)}.json",
            {"User-Agent": self.user_agent, "Accept-Encoding": "gzip, deflate"},
        )

    def company_facts(self, cik: str) -> dict[str, Any]:
        """Return raw SEC company facts JSON for a zero-padded CIK."""

        return self.transport.get_json(
            f"{self.base_url}/api/xbrl/companyfacts/CIK{format_cik(cik)}.json",
            {"User-Agent": self.user_agent, "Accept-Encoding": "gzip, deflate"},
        )

    def recent_filings_as_of(self, cik: str, as_of_date: date) -> list[FilingMetadata]:
        """Return recent filings whose filing date was available by ``as_of_date``."""

        data = self.submissions(cik)
        recent = data.get("filings", {}).get("recent", {})
        required = ("accessionNumber", "filingDate", "form", "primaryDocument")
        if not all(isinstance(recent.get(key), list) for key in required):
            raise DataSourceError("SEC submissions response missing recent filing arrays")
        count = len(recent["accessionNumber"])
        filings: list[FilingMetadata] = []
        for index in range(count):
            filing_date = date.fromisoformat(recent["filingDate"][index])
            if filing_date > as_of_date:
                continue
            accession = recent["accessionNumber"][index]
            primary_document = recent["primaryDocument"][index]
            cik_padded = format_cik(cik)
            cik_no_zeros = str(int(cik_padded))
            accession_path = accession.replace("-", "")
            filings.append(
                FilingMetadata(
                    cik=cik_padded,
                    accession_number=accession,
                    filing_date=filing_date,
                    report_date=optional_date(array_get(recent, "reportDate", index)),
                    form=recent["form"][index],
                    primary_document=primary_document,
                    source_url=(
                        "https://www.sec.gov/Archives/edgar/data/"
                        f"{cik_no_zeros}/{accession_path}/{primary_document}"
                    ),
                    retrieved_at=utc_now(),
                )
            )
        return filings


@register("sec_edgar")
def source(config: DataSourceConfig, transport: JsonTransport | None = None) -> SecEdgarClient:
    """Registered SEC EDGAR source factory."""

    return SecEdgarClient.from_config(config, transport=transport)
