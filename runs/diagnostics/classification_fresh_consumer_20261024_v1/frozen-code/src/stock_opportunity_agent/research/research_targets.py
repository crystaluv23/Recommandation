"""Frozen magnitude research-target contracts (action-plan C5, gate-passed).

A research target is a fixed projection of the existing realized labels onto
a contrast population — never a redefinition of future outcomes. Group
membership for concrete cases lives only in hash-linked group manifests and
is revealed to comparison roles (E2/H3) exclusively after the evidence pack
manifest is frozen; hypothesis and extraction roles (H1/E1) receive only the
label-free target descriptor.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Iterable, Mapping

from stock_opportunity_agent.artifacts import canonical_json_hash
from stock_opportunity_agent.models import ValidationError

MAGNITUDE_GE3_TARGET_ID = "magnitude_ge3_v1"
_GE3_HIGH = "ge3_high"
_GE3_LOW = "ge3_low"

_TARGET_GROUP_KEYS = frozenset(
    {
        "target_group",
        "ge3_group",
        "contrast_group",
        "group_label",
    }
)
_TARGET_GROUP_VALUES = frozenset({_GE3_HIGH, _GE3_LOW})


@dataclass(frozen=True)
class ResearchTargetContract:
    """One frozen contrast target over the existing realized labels."""

    target_id: str
    population: str
    high_rule: str
    low_rule: str
    version: str
    evaluation_protocol: str

    def descriptor(self) -> dict[str, Any]:
        """Label-free description safe for hypothesis/extraction payloads."""

        return {
            "target_id": self.target_id,
            "population": self.population,
            "contrast": {
                "high": self.high_rule,
                "low": self.low_rule,
            },
            "version": self.version,
            "evaluation_protocol": self.evaluation_protocol,
            "boundary": (
                "This descriptor defines a fixed projection of already realized "
                "labels for retrospective contrast research. It is not a case "
                "outcome, carries no per-case group membership, and never "
                "redefines the prediction target."
            ),
        }

    def identity_hash(self) -> str:
        return str(
            canonical_json_hash(
                {
                    "target_id": self.target_id,
                    "population": self.population,
                    "high_rule": self.high_rule,
                    "low_rule": self.low_rule,
                    "version": self.version,
                    "evaluation_protocol": self.evaluation_protocol,
                }
            )
        )


MAGNITUDE_GE3_CONTRACT = ResearchTargetContract(
    target_id=MAGNITUDE_GE3_TARGET_ID,
    population="true_surge_cases",
    high_rule="realized_max_multiple >= 3.0",
    low_rule="2.0 <= realized_max_multiple < 3.0",
    version="ge3-projection-v1",
    evaluation_protocol="ge3-paired-evaluation-v1",
)


def project_magnitude_ge3_group(realized_max_multiple: float) -> str | None:
    """Project one realized label onto the ge3 contrast; None below 2x."""

    value = float(realized_max_multiple)
    if value < 2.0:
        return None
    return _GE3_HIGH if value >= 3.0 else _GE3_LOW


def active_research_targets() -> tuple[ResearchTargetContract, ...]:
    """Targets whose data gate passed; ge10/extremes stay unimplemented."""

    return (MAGNITUDE_GE3_CONTRACT,)


def build_target_group_manifest(
    cases: Iterable[Any],
    contract: ResearchTargetContract,
) -> dict[str, Any]:
    """Map every true-surge case (including FN) onto its contrast group."""

    if contract.target_id != MAGNITUDE_GE3_TARGET_ID:
        raise ValidationError("unsupported research target for group manifest")
    assignments: dict[str, str] = {}
    for case in cases:
        case_id = str(case.case_id)
        if case_id in assignments:
            raise ValidationError("duplicate case id in target group manifest")
        realized = float(case.ground_truth.realized_max_multiple)
        group = project_magnitude_ge3_group(realized)
        if group is not None:
            assignments[case_id] = group
    payload: dict[str, Any] = {
        "schema_version": "research-target-group-manifest-v1",
        "target_id": contract.target_id,
        "target_identity_hash": contract.identity_hash(),
        "groups": dict(sorted(assignments.items())),
    }
    payload["manifest_hash"] = str(
        canonical_json_hash(
            {
                key: value
                for key, value in payload.items()
                if key != "manifest_hash"
            }
        )
    )
    return payload


def build_target_sampling_manifest(
    cases: Iterable[Any],
    contract: ResearchTargetContract,
    *,
    cycle_id: int,
    base_seed: str,
    dev_limit: int,
    check_limit: int,
) -> dict[str, Any]:
    """Issuer-disjoint dev/check sampling inside one target population."""

    import random as _random

    if contract.target_id != MAGNITUDE_GE3_TARGET_ID:
        raise ValidationError("unsupported research target for sampling")
    if dev_limit < 2 or check_limit < 2:
        raise ValidationError(
            "target sampling requires at least two cases per split"
        )
    # One case per issuer, grouped by contrast class: the split is
    # class-balanced by construction (the target's groups are its research
    # classes) and globally issuer-disjoint, so induction and paired
    # validation each see both groups.
    by_group: dict[str, list[Any]] = {"ge3_high": [], "ge3_low": []}
    seen_companies: set[str] = set()
    ordered = sorted(cases, key=lambda case: str(case.case_id))
    generator = _random.Random(f"{base_seed}:{contract.target_id}:{cycle_id}")
    generator.shuffle(ordered)
    for case in ordered:
        group = project_magnitude_ge3_group(
            float(case.ground_truth.realized_max_multiple)
        )
        if group is None or case.company_id in seen_companies:
            continue
        seen_companies.add(case.company_id)
        by_group[group].append(case)
    per_side = {
        group: max(1, limit // 2)
        for group, limit in (
            ("ge3_high", dev_limit + check_limit),
            ("ge3_low", dev_limit + check_limit),
        )
    }
    dev_ids: list[str] = []
    check_ids: list[str] = []
    for group in ("ge3_high", "ge3_low"):
        dev_take = max(1, dev_limit // 2)
        check_take = max(1, check_limit // 2)
        group_cases = by_group[group]
        dev_ids.extend(
            case.case_id for case in group_cases[:dev_take]
        )
        check_ids.extend(
            case.case_id
            for case in group_cases[dev_take : dev_take + check_take]
        )
    del per_side
    sampling = {
        "schema_version": "slow-sampling-manifest-v1",
        "seed": f"{base_seed}:{contract.target_id}",
        "dev_case_ids": dev_ids,
        "check_case_ids": check_ids,
        "issuer_groups": {
            case.case_id: case.company_id
            for case in ordered
            if case.case_id in set(dev_ids) | set(check_ids)
        },
    }
    return {
        "schema_version": "research-target-sampling-manifest-v1",
        "target_id": contract.target_id,
        "target_identity_hash": contract.identity_hash(),
        "population_case_count": sum(len(v) for v in by_group.values()),
        "sampling": sampling,
    }


def reveal_target_groups(
    *,
    frozen_evidence_pack_manifest: Mapping[str, Any],
    group_manifest: Mapping[str, Any],
) -> dict[str, Any]:
    """Reveal per-case groups only against one exact frozen evidence pack."""

    expected = group_manifest.get("target_identity_hash")
    if group_manifest.get("manifest_hash") is None or expected is None:
        raise ValidationError("target group manifest is missing identity fields")
    pack_hash = frozen_evidence_pack_manifest.get("pack_manifest_hash")
    if not str(pack_hash or ""):
        raise ValidationError("frozen evidence pack manifest hash is required")
    frozen_targets = frozen_evidence_pack_manifest.get("target_identity_hashes")
    if not isinstance(frozen_targets, Mapping) or (
        group_manifest.get("target_id") not in frozen_targets
    ):
        raise ValidationError(
            "frozen evidence pack does not cover this research target"
        )
    if str(frozen_targets[group_manifest.get("target_id")]) != str(expected):
        raise ValidationError("target contract changed after evidence freezing")
    return {
        "schema_version": "research-target-group-reveal-v1",
        "target_id": group_manifest.get("target_id"),
        "pack_manifest_hash": str(pack_hash),
        "groups": dict(group_manifest.get("groups", {})),
    }


def assert_payload_without_target_groups(value: Any, *, path: str = "payload") -> None:
    """Fail closed if any per-case contrast-group field reaches H1/E1."""

    if isinstance(value, Mapping):
        for key, nested in value.items():
            normalized = re.sub(r"[^a-z0-9]+", "_", str(key).casefold()).strip("_")
            if normalized in _TARGET_GROUP_KEYS:
                raise ValidationError(
                    f"contrast-group field leaked into label-free payload: {path}.{key}"
                )
            if (
                isinstance(nested, str)
                and nested in _TARGET_GROUP_VALUES
                and normalized.endswith("group")
            ):
                raise ValidationError(
                    f"contrast-group value leaked into label-free payload: {path}.{key}"
                )
            assert_payload_without_target_groups(nested, path=f"{path}.{key}")
    elif isinstance(value, (list, tuple)):
        for index, nested in enumerate(value):
            assert_payload_without_target_groups(nested, path=f"{path}[{index}]")
