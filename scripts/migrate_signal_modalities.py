#!/usr/bin/env python3
"""Create an explicitly classified successor from one legacy Signal Registry."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import tempfile
from dataclasses import replace
from pathlib import Path
from typing import Any, Mapping

from stock_opportunity_agent.models import ValidationError
from stock_opportunity_agent.signal_library import (
    SignalExecutionType,
    SignalModality,
    SignalRegistry,
)


SCHEMA_VERSION = "signal-modality-migration-plan-v1"
RESULT_SCHEMA_VERSION = "signal-modality-migration-result-v1"


def _canonical_hash(value: Mapping[str, Any]) -> str:
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _copy_definition_files(source: Path, target: Path) -> None:
    """Copy immutable Registry definitions without observations or journals."""

    allowed_names = {"registry.json", "manifest.json", "spec.json", "tests.json", "skill.md"}
    for path in sorted(source.rglob("*")):
        if not path.is_file() or path.name not in allowed_names:
            continue
        relative = path.relative_to(source)
        if path.name == "registry.json" and len(relative.parts) != 1:
            continue
        if path.name != "registry.json" and (
            len(relative.parts) < 3 or relative.parts[0].startswith(".")
        ):
            continue
        destination = target / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(path, destination)


def _selected_tests(
    tests: tuple[Mapping[str, Any], ...],
    names: object,
    replacements: object,
    *,
    signal_ref: str,
) -> tuple[Mapping[str, Any], ...]:
    if names is not None and replacements is not None:
        raise ValidationError(
            f"fixture_names and replacement_tests are mutually exclusive: {signal_ref}"
        )
    if replacements is not None:
        if not isinstance(replacements, list) or not replacements or any(
            not isinstance(test, Mapping) for test in replacements
        ):
            raise ValidationError(
                f"replacement_tests must be a non-empty object list: {signal_ref}"
            )
        return tuple(dict(test) for test in replacements)
    if names is None:
        return tests
    if not isinstance(names, list) or not names or any(
        not isinstance(name, str) or not name.strip() for name in names
    ):
        raise ValidationError(f"fixture_names must be a non-empty string list: {signal_ref}")
    by_name = {str(test.get("name", "")): test for test in tests}
    if len(by_name) != len(tests) or any(name not in by_name for name in names):
        raise ValidationError(f"fixture_names do not match source tests: {signal_ref}")
    if len(set(names)) != len(names):
        raise ValidationError(f"fixture_names contain duplicates: {signal_ref}")
    return tuple(by_name[name] for name in names)


def migrate_registry(
    *, source_root: Path, target_root: Path, plan: Mapping[str, Any]
) -> dict[str, Any]:
    """Apply one exact, complete modality plan to a definition-only successor."""

    if plan.get("schema_version") != SCHEMA_VERSION:
        raise ValidationError("unsupported Signal modality migration plan")
    source = SignalRegistry(source_root)
    source_snapshot = source.freeze()
    expected_version = plan.get("source_registry_version")
    expected_hash = plan.get("source_registry_hash")
    if (
        expected_version != source_snapshot.version
        or expected_hash != source_snapshot.registry_hash
    ):
        raise ValidationError("Signal modality migration source identity mismatch")

    raw_rows = plan.get("signals")
    if not isinstance(raw_rows, list) or any(
        not isinstance(row, Mapping) for row in raw_rows
    ):
        raise ValidationError("Signal modality migration signals must be an array")
    rows = {str(row.get("source_ref", "")): dict(row) for row in raw_rows}
    if len(rows) != len(raw_rows) or "" in rows:
        raise ValidationError("Signal modality migration source refs must be unique")
    current_refs = {spec.ref for spec in source_snapshot.specs}
    if set(rows) != current_refs:
        missing = sorted(current_refs - set(rows))
        extra = sorted(set(rows) - current_refs)
        raise ValidationError(
            f"Signal modality migration coverage mismatch; missing={missing}, extra={extra}"
        )
    if target_root.exists():
        raise ValidationError("Signal modality migration target already exists")

    target_root.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(
        prefix=f".{target_root.name}-", dir=target_root.parent
    ) as temporary:
        staged_root = Path(temporary) / "registry"
        _copy_definition_files(source_root, staged_root)
        target = SignalRegistry(staged_root)
        staged_source = target.freeze()
        if (
            staged_source.version != source_snapshot.version
            or staged_source.registry_hash != source_snapshot.registry_hash
        ):
            raise ValidationError("copied Signal Registry differs from source")

        migrations: list[dict[str, Any]] = []
        for legacy in sorted(source_snapshot.specs, key=lambda spec: spec.ref):
            row = rows[legacy.ref]
            try:
                modality = SignalModality(str(row["modality"]))
            except (KeyError, ValueError) as exc:
                raise ValidationError(
                    f"invalid modality classification: {legacy.ref}"
                ) from exc
            execution = row.get("execution")
            if execution is None:
                execution_type = legacy.execution_type
                function = legacy.function
                skill_file = legacy.skill_file
            else:
                if not isinstance(execution, Mapping):
                    raise ValidationError(f"execution override must be an object: {legacy.ref}")
                try:
                    execution_type = SignalExecutionType(str(execution["type"]))
                except (KeyError, ValueError) as exc:
                    raise ValidationError(
                        f"invalid execution override: {legacy.ref}"
                    ) from exc
                function = (
                    str(execution["function"])
                    if execution.get("function") is not None
                    else None
                )
                skill_file = (
                    str(execution["skill_file"])
                    if execution.get("skill_file") is not None
                    else None
                )
            parameters = dict(legacy.parameters)
            overrides = row.get("parameter_overrides", {})
            if not isinstance(overrides, Mapping):
                raise ValidationError(
                    f"parameter_overrides must be an object: {legacy.ref}"
                )
            parameters.update(overrides)
            successor = replace(
                legacy,
                version=legacy.version + 1,
                modality=modality,
                description=str(row.get("description", legacy.description)),
                execution_type=execution_type,
                function=function,
                skill_file=skill_file,
                parameters=parameters,
            )
            tests = _selected_tests(
                source.load_tests(legacy.ref),
                row.get("fixture_names"),
                row.get("replacement_tests"),
                signal_ref=legacy.ref,
            )
            skill = source.load_skill(legacy.ref) if execution_type is SignalExecutionType.LLM else None
            target.register_stable(successor, skill=skill, tests=tests)
            migrations.append(
                {
                    "source_ref": legacy.ref,
                    "target_ref": successor.ref,
                    "modality": successor.modality.value,
                    "source_execution": legacy.execution_type.value,
                    "target_execution": successor.execution_type.value,
                    "change": (
                        "executor_correction"
                        if legacy.execution_type is not successor.execution_type
                        else "modality_backfill"
                    ),
                }
            )

        target.bump_version()
        target_snapshot = target.freeze()
        if target_snapshot.version != source_snapshot.version + 1:
            raise ValidationError("successor Registry version did not advance once")
        if any(spec.modality is None for spec in target_snapshot.specs):
            raise ValidationError("successor Registry contains unclassified Signals")
        counts = {
            modality.value: sum(
                spec.modality is modality for spec in target_snapshot.specs
            )
            for modality in SignalModality
        }
        result = {
            "schema_version": RESULT_SCHEMA_VERSION,
            "plan_hash": _canonical_hash(dict(plan)),
            "source_registry_version": source_snapshot.version,
            "source_registry_hash": source_snapshot.registry_hash,
            "target_registry_version": target_snapshot.version,
            "target_registry_hash": target_snapshot.registry_hash,
            "signal_count": len(target_snapshot.specs),
            "modality_counts": counts,
            "capability_audit": target.audit_capabilities().to_dict(),
            "migrations": migrations,
        }
        os.replace(staged_root, target_root)

    manifest_path = target_root.parent / "modality_migration.json"
    manifest_path.write_text(
        json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-registry", type=Path, required=True)
    parser.add_argument("--target-registry", type=Path, required=True)
    parser.add_argument("--plan", type=Path, required=True)
    parser.add_argument("--report", type=Path)
    args = parser.parse_args()
    plan = json.loads(args.plan.read_text(encoding="utf-8"))
    result = migrate_registry(
        source_root=args.source_registry,
        target_root=args.target_registry,
        plan=plan,
    )
    if args.report is not None:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(
            json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
