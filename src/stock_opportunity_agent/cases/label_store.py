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
from datetime import date, datetime
from pathlib import Path
from typing import Any, Callable, Iterable, Mapping

from stock_opportunity_agent.cases.outcomes import (
    SURGE_LABEL_CONTRACT,
    six_month_smoothed_multiple,
)
from stock_opportunity_agent.models import ValidationError
from stock_opportunity_agent.data.json_stream import StreamingJSONReader

LABEL_STORE_VERSION = 1
_MANIFEST_NAME = "manifest.json"
_RECORDS_NAME = "labels.jsonl"
_MAGNITUDE_CLASSES = ("2-3x", "3-10x", "10x+")
_CASE_KEY_PATTERN = re.compile(r"^(cik_[0-9]+):([0-9]{4}-[0-9]{2}-[0-9]{2})$")


def _strict_pairs(pairs):
    value={}
    for key,item in pairs:
        if key in value:
            raise ValidationError("duplicate JSON field: "+key)
        value[key]=item
    return value


def _invalid_constant(value):
    raise ValidationError("nonfinite JSON number: "+value)


def _decoder():
    return json.JSONDecoder(object_pairs_hook=_strict_pairs,parse_constant=_invalid_constant)


def _iso_date(value,name):
    if not isinstance(value,str) or not re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}",value):
        raise ValidationError(name+" must be a canonical ISO date")
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise ValidationError(name+" must be a valid ISO date") from exc


def _positive_number(value,name):
    try:
        valid=type(value) in (int,float) and math.isfinite(value) and value>0
    except (TypeError,ValueError,OverflowError):
        valid=False
    if not valid:
        raise ValidationError(name+" must be finite and positive JSON number")


def _read_object(path):
    try:
        value=_decoder().decode(path.read_text(encoding="utf-8"))
    except (OSError,UnicodeError,ValueError,TypeError) as exc:
        raise ValidationError("cannot read valid label JSON: "+str(path)) from exc
    if not isinstance(value,dict):
        raise ValidationError("label JSON must be an object: "+str(path))
    return value


def _label_lines(path):
    try:
        with path.open(encoding="utf-8") as handle:
            yield from enumerate(handle,start=1)
    except (OSError,UnicodeError) as exc:
        raise ValidationError("cannot read label records: "+str(path)) from exc


def _verify_archive(manifest,records):
    archive=Path(manifest["archive_path"])
    if not archive.is_file():
        raise ValidationError("label archive must be a readable file")
    grouped={}
    for record in records.values():
        grouped.setdefault(record.symbol,[]).append(record)
    try:
        reader=StreamingJSONReader(archive,decoder=_decoder(),with_hash=True,strict_whitespace=True)
    except (OSError,UnicodeError) as exc:
        raise ValidationError("cannot open label archive") from exc
    keys=set(); symbols=set(); verified=set()
    try:
        reader.consume("{")
        while reader.peek()!="}":
            key=reader.decode()
            if not isinstance(key,str) or key in keys:
                raise ValidationError("label archive has invalid or duplicate object keys")
            keys.add(key);reader.consume(":")
            if key!="bars_by_symbol":
                reader.decode()
            else:
                reader.consume("{")
                while reader.peek()!="}":
                    symbol=reader.decode()
                    if not isinstance(symbol,str) or not symbol.strip() or symbol in symbols:
                        raise ValidationError("label archive has invalid or duplicate symbols")
                    symbols.add(symbol);reader.consume(":");bars=reader.decode()
                    if not isinstance(bars,list) or any(not isinstance(bar,dict) for bar in bars):
                        raise ValidationError("label archive history must be an array of price objects")
                    if symbol in grouped:
                        dates=set()
                        for bar in bars:
                            observed=_iso_date(bar.get("as_of_date"),"archive as_of_date")
                            if observed in dates:
                                raise ValidationError("label archive contains duplicate observation dates")
                            dates.add(observed)
                            _positive_number(bar.get("adjusted_close"),"archive adjusted_close")
                            if "symbol" in bar and bar["symbol"]!=symbol:
                                raise ValidationError("label archive row symbol differs from enclosing symbol")
                        for record in grouped[symbol]:
                            measured=six_month_smoothed_multiple(bars,date.fromisoformat(record.as_of_date))
                            original=record.to_dict()
                            if any(original[key]!=value for key,value in measured.items()):
                                raise ValidationError("label record disagrees with frozen archive/calculator: "+str(record.key))
                            verified.add(record.key)
                    if reader.peek()!=",": break
                    reader.consume(",")
                    if reader.peek()=="}":
                        raise ValidationError("label archive contains a trailing comma")
                reader.consume("}")
            if reader.peek()!=",": break
            reader.consume(",")
            if reader.peek()=="}":
                raise ValidationError("label archive contains a trailing comma")
        reader.consume("}");reader.finish()
        if reader.content_sha256!=manifest["archive_sha256"]:
            raise ValidationError("label archive SHA256 differs from manifest")
        if "bars_by_symbol" not in keys or verified!=set(records):
            raise ValidationError("label archive is missing required symbol histories")
    except (OSError,UnicodeError,ValueError,TypeError,KeyError,IndexError,OverflowError) as exc:
        raise ValidationError("invalid label archive or derived observation: "+str(exc)) from exc
    finally:
        reader.close()


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
        for name in ("company_id","as_of_date","symbol","horizon_end"):
            if not isinstance(getattr(self,name),str):
                raise ValidationError("label "+name+" must be text")
        if type(self.is_surge) is not bool:
            raise ValidationError("label is_surge must be a JSON boolean")
        if self.magnitude is not None and not isinstance(self.magnitude,str):
            raise ValidationError("label magnitude must be text or null")
        for name in ("baseline_dates","future_peak_dates"):
            values=getattr(self,name)
            if not isinstance(values,(list,tuple)):
                raise ValidationError("label "+name+" must be an array")
            object.__setattr__(self,name,tuple(values))
            for item in values: _iso_date(item,"label "+name)
        _iso_date(self.as_of_date,"label as_of_date")
        _iso_date(self.horizon_end,"label horizon_end")
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
            _positive_number(value,"label "+name)
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
        if not isinstance(data,Mapping):
            raise ValidationError("label record must be an object")
        missing = sorted(required - set(data))
        if missing:
            raise ValidationError(
                "label record is missing fields: " + ", ".join(missing)
            )
        if set(data)!=required:
            raise ValidationError("label record contains unknown fields")
        return cls(
            company_id=data["company_id"],
            as_of_date=data["as_of_date"],
            symbol=data["symbol"],
            baseline_mean=data["baseline_mean"],
            baseline_dates=data["baseline_dates"],
            future_peak_mean=data["future_peak_mean"],
            future_peak_dates=data["future_peak_dates"],
            horizon_end=data["horizon_end"],
            realized_max_multiple=data["realized_max_multiple"],
            is_surge=data["is_surge"],
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
        """Verify the bound archive, contract and every derived label before admission."""
        root = Path(path)
        manifest_path = root / _MANIFEST_NAME
        records_path = root / _RECORDS_NAME
        if not manifest_path.is_file() or not records_path.is_file():
            raise ValidationError(
                f"label store is incomplete at {root}: expected "
                f"{_MANIFEST_NAME} and {_RECORDS_NAME}"
            )
        manifest = _read_object(manifest_path)
        for field in (
            "store_version", "label_contract", "archive_path", "archive_sha256",
            "calculator", "created_at", "record_count",
        ):
            if field not in manifest:
                raise ValidationError(f"label store manifest lacks {field}")
        if type(manifest["store_version"]) is not int or manifest["store_version"] != LABEL_STORE_VERSION:
            raise ValidationError(
                f"unsupported label store version {manifest['store_version']} "
                f"(expected {LABEL_STORE_VERSION})"
            )
        if type(manifest["record_count"]) is not int or manifest["record_count"]<0:
            raise ValidationError("label record_count must be a nonnegative JSON integer")
        for name in ("archive_path","archive_sha256","calculator","created_at"):
            if not isinstance(manifest[name],str) or not manifest[name].strip():
                raise ValidationError("label manifest "+name+" must be nonempty text")
        if not re.fullmatch(r"[0-9a-f]{64}",manifest["archive_sha256"]):
            raise ValidationError("label archive SHA256 must be lowercase hexadecimal")
        if manifest["calculator"]!="stock_opportunity_agent.cases.outcomes.six_month_smoothed_multiple":
            raise ValidationError("label calculator identity is unsupported")
        if manifest["label_contract"]!=SURGE_LABEL_CONTRACT:
            raise ValidationError("label contract differs from the fixed outcome definition")
        try:
            created=datetime.fromisoformat(manifest["created_at"])
            if created.tzinfo is None or created.utcoffset() is None:
                raise ValueError("naive creation time")
        except ValueError as exc:
            raise ValidationError("label created_at must be an aware ISO timestamp") from exc
        records: dict[tuple[str, str], LabelRecord] = {}
        for line_number,line in _label_lines(records_path):
            if not line.strip():
                continue
            try:
                record = LabelRecord.from_dict(_decoder().decode(line))
            except (ValidationError,ValueError,TypeError,KeyError,OverflowError) as exc:
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
        _verify_archive(manifest,records)
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
