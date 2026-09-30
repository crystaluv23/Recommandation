"""Canonical retrospective outcome labels: one global store, one loader.

The label store is the single source of ground truth for every test, harness,
evaluation, and experiment. Records are keyed by ``(company_id, as_of_date)``
and persist the raw smoothed observation plus the derived surge label,
recomputed by the shared ``six_month_smoothed_multiple`` calculator from a
frozen adjusted-price archive whose identity the manifest binds.

This module is an evaluation-path artifact. Prediction-time and blind-analysis
code must not import it: labels contain post-``as_of`` information by design.

Usage example::

    store = LabelStore.load(REPO / "runs/cold_start/data/outcome-label-store-v1")
    truth = store.ground_truth("cik_0000316709", "2025-05-30")
    # truth maps to the derived record fields: realized_max_multiple (float),
    # is_surge (bool), magnitude (class or None).
"""

from __future__ import annotations

import hashlib
import json
import math
import re
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any, Callable, Iterable, Mapping

from stock_opportunity_agent.cases.outcomes import (
    SURGE_LABEL_CONTRACT,
    six_month_smoothed_multiple,
)
from stock_opportunity_agent.models import ValidationError

LABEL_STORE_VERSION = 1
_MANIFEST_NAME = "manifest.json"
_RECORDS_NAME = "labels.jsonl"
_MAGNITUDE_CLASSES = ("2-3x", "3-10x", "10x+")
_CASE_KEY_PATTERN = re.compile(r"^(cik_[0-9]+):([0-9]{4}-[0-9]{2}-[0-9]{2})$")


@dataclass(frozen=True)
class LabelRecord:
    """One derived outcome observation for a (company, prediction boundary)."""

    company_id: str
    as_of_date: str
    symbol: str
    baseline_mean: float
    baseline_dates: tuple[str, ...]
    future_peak_mean: float
    future_peak_dates: tuple[str, ...]
    horizon_end: str
    realized_max_multiple: float
    is_surge: bool
    magnitude: str | None

    def __post_init__(self) -> None:
        if not re.fullmatch(r"cik_[0-9]+", self.company_id):
            raise ValidationError("label company_id must be a cik identifier")
        try:
            date.fromisoformat(self.as_of_date)
            date.fromisoformat(self.horizon_end)
            for value in (*self.baseline_dates, *self.future_peak_dates):
                date.fromisoformat(value)
        except ValueError as exc:
            raise ValidationError(f"label dates must be ISO dates: {exc}") from exc
        if not self.symbol.strip():
            raise ValidationError("label symbol must not be empty")
        for name, value in (
            ("baseline_mean", self.baseline_mean),
            ("future_peak_mean", self.future_peak_mean),
            ("realized_max_multiple", self.realized_max_multiple),
        ):
            if not math.isfinite(value) or value <= 0:
                raise ValidationError(f"label {name} must be finite and positive")
        if len(self.baseline_dates) != 5 or len(set(self.baseline_dates)) != 5:
            raise ValidationError("label baseline requires five distinct dates")
        if len(self.future_peak_dates) != 5 or len(set(self.future_peak_dates)) != 5:
            raise ValidationError("label future peak requires five distinct dates")
        if self.is_surge != (self.realized_max_multiple >= 2.0):
            raise ValidationError("label is_surge disagrees with the 2.0 threshold")
        if self.realized_max_multiple >= 10.0:
            expected_magnitude: str | None = "10x+"
        elif self.realized_max_multiple >= 3.0:
            expected_magnitude = "3-10x"
        elif self.realized_max_multiple >= 2.0:
            expected_magnitude = "2-3x"
        else:
            expected_magnitude = None
        if self.magnitude != expected_magnitude:
            raise ValidationError("label magnitude disagrees with the multiple")

    @property
    def key(self) -> tuple[str, str]:
        return (self.company_id, self.as_of_date)

    def to_dict(self) -> dict[str, Any]:
        return {
            "company_id": self.company_id,
            "as_of_date": self.as_of_date,
            "symbol": self.symbol,
            "baseline_mean": self.baseline_mean,
            "baseline_dates": list(self.baseline_dates),
            "future_peak_mean": self.future_peak_mean,
            "future_peak_dates": list(self.future_peak_dates),
            "horizon_end": self.horizon_end,
            "realized_max_multiple": self.realized_max_multiple,
            "is_surge": self.is_surge,
            "magnitude": self.magnitude,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "LabelRecord":
        required = {
            "company_id", "as_of_date", "symbol", "baseline_mean",
            "baseline_dates", "future_peak_mean", "future_peak_dates",
            "horizon_end", "realized_max_multiple", "is_surge", "magnitude",
        }
        missing = sorted(required - set(data))
        if missing:
            raise ValidationError(
                "label record is missing fields: " + ", ".join(missing)
            )
        return cls(
            company_id=str(data["company_id"]),
            as_of_date=str(data["as_of_date"]),
            symbol=str(data["symbol"]),
            baseline_mean=float(data["baseline_mean"]),
            baseline_dates=tuple(str(item) for item in data["baseline_dates"]),
            future_peak_mean=float(data["future_peak_mean"]),
            future_peak_dates=tuple(str(item) for item in data["future_peak_dates"]),
            horizon_end=str(data["horizon_end"]),
            realized_max_multiple=float(data["realized_max_multiple"]),
            is_surge=bool(data["is_surge"]),
            magnitude=data["magnitude"],
        )


class UnknownLabelError(ValidationError):
    """No label exists for the requested (company_id, as_of_date) key."""


class LabelStore:
    """Loaded, verified view of one immutable label-store directory."""

    def __init__(
        self,
        *,
        manifest: Mapping[str, Any],
        records: dict[tuple[str, str], LabelRecord],
    ) -> None:
        self.manifest: dict[str, Any] = dict(manifest)
        self._records = records

    @classmethod
    def load(cls, path: str | Path) -> "LabelStore":
        root = Path(path)
        manifest_path = root / _MANIFEST_NAME
        records_path = root / _RECORDS_NAME
        if not manifest_path.is_file() or not records_path.is_file():
            raise ValidationError(
                f"label store is incomplete at {root}: expected "
                f"{_MANIFEST_NAME} and {_RECORDS_NAME}"
            )
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        for field in (
            "store_version", "label_contract", "archive_path", "archive_sha256",
            "calculator", "created_at", "record_count",
        ):
            if field not in manifest:
                raise ValidationError(f"label store manifest lacks {field}")
        if int(manifest["store_version"]) != LABEL_STORE_VERSION:
            raise ValidationError(
                f"unsupported label store version {manifest['store_version']} "
                f"(expected {LABEL_STORE_VERSION})"
            )
        records: dict[tuple[str, str], LabelRecord] = {}
        with records_path.open(encoding="utf-8") as handle:
            for line_number, line in enumerate(handle, start=1):
                if not line.strip():
                    continue
                try:
                    record = LabelRecord.from_dict(json.loads(line))
                except ValidationError as exc:
                    raise ValidationError(
                        f"invalid label record at {records_path}:{line_number}: {exc}"
                    ) from exc
                if record.key in records:
                    raise ValidationError(
                        f"duplicate label key {record.key} at "
                        f"{records_path}:{line_number}"
                    )
                records[record.key] = record
        if len(records) != int(manifest["record_count"]):
            raise ValidationError(
                f"label store manifest declares {manifest['record_count']} "
                f"records but {len(records)} loaded"
            )
        return cls(manifest=manifest, records=records)

    def __len__(self) -> int:
        return len(self._records)

    def keys(self) -> tuple[tuple[str, str], ...]:
        return tuple(sorted(self._records))

    def record(self, company_id: str, as_of: str | date) -> LabelRecord:
        key = (company_id, _normalize_as_of(as_of))
        record = self._records.get(key)
        if record is None:
            near = sorted(
                other
                for other in self._records
                if other[0] == company_id or other[1] == key[1]
            )[:8]
            raise UnknownLabelError(
                f"no label for {key}; nearest stored keys: {near or 'none'}"
            )
        return record

    def ground_truth(self, company_id: str, as_of: str | date) -> dict[str, Any]:
        record = self.record(company_id, as_of)
        return {
            "realized_max_multiple": record.realized_max_multiple,
            "is_surge": record.is_surge,
            "magnitude": record.magnitude,
        }

    def label_contract(self) -> dict[str, Any]:
        return dict(self.manifest["label_contract"])


def build_label_records(
    bars_by_symbol: Mapping[str, Any],
    pairs: Iterable[tuple[str, str]],
    symbol_by_company: Mapping[str, str],
    *,
    calculator: Callable[
        [Any, date], dict[str, Any]
    ] = six_month_smoothed_multiple,
) -> tuple[list[LabelRecord], list[dict[str, Any]]]:
    """Derive label records for (company_id, as_of) pairs from price bars.

    Returns (records, exclusions); every failure becomes one explicit exclusion
    row with a reason instead of a default label.
    """

    records: list[LabelRecord] = []
    exclusions: list[dict[str, Any]] = []
    for company_id, as_of_text in pairs:
        as_of_date = _normalize_as_of(as_of_text)
        symbol = symbol_by_company.get(company_id)
        if not symbol:
            exclusions.append(
                {"company_id": company_id, "as_of_date": as_of_date,
                 "reason": "no_symbol_mapping"}
            )
            continue
        raw_bars = bars_by_symbol.get(symbol)
        try:
            label = calculator(raw_bars, date.fromisoformat(as_of_date))
        except ValidationError as exc:
            exclusions.append(
                {"company_id": company_id, "as_of_date": as_of_date,
                 "symbol": symbol, "reason": str(exc)}
            )
            continue
        records.append(
            LabelRecord(
                company_id=company_id,
                as_of_date=as_of_date,
                symbol=symbol,
                baseline_mean=float(label["baseline_mean"]),
                baseline_dates=tuple(label["baseline_dates"]),
                future_peak_mean=float(label["future_peak_mean"]),
                future_peak_dates=tuple(label["future_peak_dates"]),
                horizon_end=str(label["horizon_end"]),
                realized_max_multiple=float(label["realized_max_multiple"]),
                is_surge=bool(label["is_surge"]),
                magnitude=label["magnitude"],
            )
        )
    return records, exclusions


def write_label_store(
    root: str | Path,
    *,
    records: Iterable[LabelRecord],
    archive_path: str | Path,
    archive_sha256: str,
    created_at: str,
) -> None:
    """Persist one immutable label-store directory version."""

    directory = Path(root)
    directory.mkdir(parents=True, exist_ok=False)
    rows = [record.to_dict() for record in records]
    with (directory / _RECORDS_NAME).open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, sort_keys=True) + "\n")
    manifest = {
        "store_version": LABEL_STORE_VERSION,
        "label_contract": dict(SURGE_LABEL_CONTRACT),
        "archive_path": str(archive_path),
        "archive_sha256": archive_sha256,
        "calculator": (
            "stock_opportunity_agent.cases.outcomes.six_month_smoothed_multiple"
        ),
        "created_at": created_at,
        "record_count": len(rows),
    }
    (directory / _MANIFEST_NAME).write_text(
        json.dumps(manifest, indent=1, sort_keys=True) + "\n", encoding="utf-8"
    )


def _normalize_as_of(value: str | date) -> str:
    if isinstance(value, date):
        return value.isoformat()
    text = str(value).strip()
    return date.fromisoformat(text).isoformat()


def parse_case_key(case_id: str) -> tuple[str, str]:
    """Split a ``cik_...:YYYY-MM-DD`` case key into its label-store key."""

    match = _CASE_KEY_PATTERN.match(str(case_id))
    if not match:
        raise ValidationError(f"cannot parse case key: {case_id!r}")
    return match.group(1), match.group(2)


def file_sha256(path: str | Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()
