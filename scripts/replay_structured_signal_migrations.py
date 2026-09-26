#!/usr/bin/env python3
"""Replay legacy LLM financial Signals as deterministic structured v2 specs."""

from __future__ import annotations

import argparse
import hashlib
import json
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable, Mapping

from stock_opportunity_agent.data.raw_info import RawInfoDocument
from stock_opportunity_agent.models import ValidationError
from stock_opportunity_agent.signal_library import (
    SignalExecutionType,
    SignalModality,
    SignalRegistry,
    SignalResult,
    SignalSpec,
    SignalValue,
    default_deterministic_signal_functions,
    validate_signal_result,
)


TARGET_FUNCTIONS = {
    "cash_to_current_liabilities_ratio": (
        "financial.cash_to_current_liabilities_ratio"
    ),
    "cash_burn_rate_elevated": "financial.cash_burn_rate_elevated",
    "liquidity_runway_months": "financial.liquidity_runway_months",
}
TARGET_DESCRIPTIONS = {
    "cash_to_current_liabilities_ratio": (
        "Measure the ratio of latest cash and equivalents to current liabilities "
        "for the same point-in-time period and reported currency."
    ),
    "cash_burn_rate_elevated": (
        "Measure absolute negative operating cash flow divided by the closest "
        "same-currency cash balance at or before the reported period end."
    ),
    "liquidity_runway_months": (
        "Measure cash runway in months from the latest negative operating cash "
        "flow duration and closest same-currency cash balance."
    ),
}


def build_migration_spec(legacy: SignalSpec) -> SignalSpec:
    """Return the deterministic v2 correction for one supported legacy v1."""

    try:
        function = TARGET_FUNCTIONS[legacy.signal_id]
    except KeyError as exc:
        raise ValidationError(
            f"unsupported structured Signal migration: {legacy.ref}"
        ) from exc
    parameters = dict(legacy.parameters)
    if legacy.signal_id == "cash_burn_rate_elevated":
        parameters.setdefault("max_period_age_days", 550)
    if legacy.signal_id == "liquidity_runway_months":
        parameters.setdefault("max_period_age_days", 365)
    return SignalSpec(
        signal_id=legacy.signal_id,
        version=legacy.version + 1,
        category=legacy.category,
        description=TARGET_DESCRIPTIONS[legacy.signal_id],
        execution_type=SignalExecutionType.DETERMINISTIC,
        source_types=legacy.source_types,
        modality=SignalModality.STRUCTURED,
        evidence_policy=legacy.evidence_policy,
        function=function,
        parameters=parameters,
        retrieval_policy=legacy.retrieval_policy,
    )


def _historical_result(
    results: Iterable[Mapping[str, Any]], signal_id: str, version: int
) -> Mapping[str, Any]:
    matches = [
        row
        for row in results
        if row.get("signal_id") == signal_id and int(row.get("version", 0)) == version
    ]
    if len(matches) != 1:
        raise ValidationError(
            f"expected one historical result for {signal_id}:v{version}; "
            f"found {len(matches)}"
        )
    return matches[0]


def _load_frozen_documents(
    raw_info_root: Path,
    document_cache: dict[str, RawInfoDocument],
    fingerprints: Iterable[str],
    *,
    company_id: str,
    as_of: datetime,
) -> tuple[RawInfoDocument, ...]:
    documents: list[RawInfoDocument] = []
    for fingerprint in fingerprints:
        try:
            document_id, content_hash = str(fingerprint).rsplit(":", 1)
        except ValueError as exc:
            raise ValidationError(
                f"invalid frozen document fingerprint: {fingerprint}"
            ) from exc
        document = document_cache.get(document_id)
        if document is None:
            paths = list(
                raw_info_root.glob(f"*/{company_id}/{document_id}.json")
            )
            if len(paths) != 1:
                raise ValidationError(
                    f"expected one frozen raw document for {document_id}; "
                    f"found {len(paths)}"
                )
            document = RawInfoDocument.from_dict(
                json.loads(paths[0].read_text(encoding="utf-8"))
            )
            document_cache[document_id] = document
        if document.available_at > as_of:
            raise ValidationError(
                f"frozen document exceeds prediction time: {document_id}"
            )
        if document.content_hash != content_hash:
            raise ValidationError(
                f"frozen content hash mismatch for {document_id}: "
                f"{content_hash} != {document.content_hash}"
            )
        documents.append(document)
    return tuple(documents)


def replay(
    *,
    run_root: Path,
    raw_info_root: Path,
) -> dict[str, Any]:
    """Execute deterministic v2 over exact persisted v1 inputs, then summarize."""

    registry = SignalRegistry(run_root / "signals")
    functions = default_deterministic_signal_functions()
    specs = {
        signal_id: build_migration_spec(registry.latest_spec(signal_id))
        for signal_id in TARGET_FUNCTIONS
    }
    rows: list[dict[str, Any]] = []
    document_cache: dict[str, RawInfoDocument] = {}
    trajectory_count = 0
    trajectory_paths = sorted((run_root / "experiments" / "trajectories").rglob("*.json"))
    for path in trajectory_paths:
        payload = json.loads(path.read_text(encoding="utf-8"))
        trajectory = payload.get("trajectory")
        if not isinstance(trajectory, Mapping):
            continue
        trajectory_count += 1
        as_of = datetime.fromisoformat(str(trajectory["prediction_time"]))
        ground_truth = dict(trajectory.get("ground_truth", {}))
        is_surge = bool(ground_truth.get("is_surge"))
        for round_index, signal_round in enumerate(trajectory.get("signal_rounds", ())):
            batch = dict(signal_round.get("batch", {}))
            fingerprints_by_ref = dict(batch.get("document_fingerprints", {}))
            for signal_id, spec in specs.items():
                legacy_ref = f"{signal_id}:v{spec.version - 1}"
                if legacy_ref not in fingerprints_by_ref:
                    continue
                old = _historical_result(
                    batch.get("results", ()), signal_id, spec.version - 1
                )
                fingerprints = tuple(fingerprints_by_ref[legacy_ref])
                documents = _load_frozen_documents(
                    raw_info_root,
                    document_cache,
                    fingerprints,
                    company_id=str(trajectory["company_id"]),
                    as_of=as_of,
                )
                function = functions[str(spec.function)]
                new_result: SignalResult = function(spec, documents, as_of)
                validate_signal_result(spec, new_result, documents, as_of=as_of)
                old_state = str(dict(old.get("state", {})).get("value"))
                old_confidence = float(
                    dict(old.get("state", {})).get("confidence", 0.0)
                )
                rows.append(
                    {
                        "case_id": trajectory["case_id"],
                        "company_id": trajectory["company_id"],
                        "prediction_time": trajectory["prediction_time"],
                        "round_index": round_index,
                        "legacy_ref": legacy_ref,
                        "migration_ref": spec.ref,
                        "document_fingerprints": list(fingerprints),
                        "document_count": len(documents),
                        "old_state": old_state,
                        "old_confidence": old_confidence,
                        "new_state": new_result.value.value,
                        "new_confidence": new_result.confidence,
                        "new_interpretation": new_result.interpretation,
                        "new_evidence": [
                            item.to_dict() for item in new_result.supporting_evidence
                        ],
                        "state_agreement": old_state == new_result.value.value,
                        "is_surge_post_execution_audit": is_surge,
                    }
                )

    by_signal: dict[str, Any] = {}
    for signal_id, spec in specs.items():
        signal_rows = [row for row in rows if row["migration_ref"] == spec.ref]
        transition_counts = Counter(
            f"{row['old_state']}->{row['new_state']}" for row in signal_rows
        )
        label_state_counts: dict[str, Counter[str]] = defaultdict(Counter)
        for row in signal_rows:
            group = "surge" if row["is_surge_post_execution_audit"] else "control"
            label_state_counts[group][row["new_state"]] += 1
        by_signal[signal_id] = {
            "legacy_ref": f"{signal_id}:v{spec.version - 1}",
            "migration_spec": spec.to_dict(),
            "occurrences": len(signal_rows),
            "state_agreements": sum(row["state_agreement"] for row in signal_rows),
            "old_available": sum(row["old_state"] != SignalValue.UNAVAILABLE.value for row in signal_rows),
            "new_available": sum(row["new_state"] != SignalValue.UNAVAILABLE.value for row in signal_rows),
            "old_mean_confidence": (
                sum(row["old_confidence"] for row in signal_rows) / len(signal_rows)
                if signal_rows
                else None
            ),
            "new_mean_confidence": (
                sum(row["new_confidence"] for row in signal_rows) / len(signal_rows)
                if signal_rows
                else None
            ),
            "transitions": dict(sorted(transition_counts.items())),
            "post_execution_label_state_counts": {
                group: dict(sorted(counts.items()))
                for group, counts in sorted(label_state_counts.items())
            },
        }
    source_identity = hashlib.sha256(
        json.dumps(
            {
                "run_root": str(run_root),
                "document_fingerprints": sorted(
                    {
                        fingerprint
                        for row in rows
                        for fingerprint in row["document_fingerprints"]
                    }
                ),
                "trajectory_files": [str(path.relative_to(run_root)) for path in trajectory_paths],
            },
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()
    return {
        "schema_version": "structured-signal-migration-replay-v1",
        "source_run": str(run_root),
        "raw_info_root": str(raw_info_root),
        "source_identity": source_identity,
        "execution_label_blind": True,
        "registry_mutated": False,
        "trajectory_count": trajectory_count,
        "occurrence_count": len(rows),
        "signals": by_signal,
        "rows": rows,
    }


def render_markdown(report: Mapping[str, Any]) -> str:
    """Render a concise human-readable replay report."""

    lines = [
        "# Structured Signal migration replay",
        "",
        f"- Source run: `{report['source_run']}`",
        f"- Frozen trajectories: {report['trajectory_count']}",
        f"- Replayed Signal occurrences: {report['occurrence_count']}",
        "- Execution boundary: exact persisted document ids, content hashes, and prediction timestamps; labels were read only after execution for audit grouping.",
        "- Registry mutation: none.",
        "",
        "| Signal | Uses | State agreement | Availability old -> new | Mean confidence old -> new |",
        "|---|---:|---:|---:|---:|",
    ]
    transition_lines: list[str] = []
    for signal_id, row in report["signals"].items():
        occurrences = int(row["occurrences"])
        agreement = (
            f"{row['state_agreements']}/{occurrences}" if occurrences else "0/0"
        )
        old_confidence = row["old_mean_confidence"]
        new_confidence = row["new_mean_confidence"]
        confidence = (
            f"{old_confidence:.3f} -> {new_confidence:.3f}"
            if old_confidence is not None and new_confidence is not None
            else "n/a"
        )
        lines.append(
            f"| `{signal_id}` | {occurrences} | {agreement} | "
            f"{row['old_available']} -> {row['new_available']} | {confidence} |"
        )
        transitions = ", ".join(
            f"`{key}`: {value}" for key, value in row["transitions"].items()
        ) or "none"
        transition_lines.append(
            f"- Transitions for `{signal_id}`: {transitions}."
        )
    lines.extend(["", *transition_lines])
    lines.extend(
        [
            "",
            "## Interpretation",
            "",
            "- Cash/current-liabilities differences are resolved by matched typed facts and the declared ratio thresholds; complete inputs can turn an LLM abstention or neutral state into a measured state.",
            "- Cash-burn differences come from explicit numeric semantics: zero burn is negative evidence, while a positive but below-threshold burn is neutral; complete matched facts can also recover an old LLM abstention.",
            "- Runway differences primarily occur when operating cash flow is non-negative. The deterministic v2 treats that as negative evidence of a low-runway condition instead of converting cash generation into burn; finite runways use the declared six- and twelve-month boundaries.",
            "- Deterministic confidence `1.0` means the declared formula was completely evaluated from validated inputs. It is execution confidence, not confidence that the Signal predicts a surge.",
            "",
            "The label-group counts are post-execution diagnostics. They did not enter the deterministic functions or their input selection. This replay measures execution replacement on historical inputs; it does not rerun the final prediction LLM, so changed Signal states are downstream-impact candidates rather than causal prediction changes.",
            "",
        ]
    )
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-root", type=Path, required=True)
    parser.add_argument("--raw-info-root", type=Path, required=True)
    parser.add_argument("--output-json", type=Path, required=True)
    parser.add_argument("--output-md", type=Path, required=True)
    args = parser.parse_args()
    report = replay(run_root=args.run_root, raw_info_root=args.raw_info_root)
    args.output_json.parent.mkdir(parents=True, exist_ok=True)
    args.output_md.parent.mkdir(parents=True, exist_ok=True)
    args.output_json.write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    args.output_md.write_text(render_markdown(report), encoding="utf-8")
    print(json.dumps({key: report[key] for key in ("trajectory_count", "occurrence_count")}))


if __name__ == "__main__":
    main()
