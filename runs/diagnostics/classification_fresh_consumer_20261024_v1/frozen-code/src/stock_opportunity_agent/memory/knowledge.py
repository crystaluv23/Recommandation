"""Shared, bounded use-context and observational performance for knowledge cards."""

from __future__ import annotations

import json
import re
from collections import defaultdict
from pathlib import Path
from typing import Any, Iterable, Mapping

from stock_opportunity_agent.artifacts import atomic_write_json, canonical_json_hash
from stock_opportunity_agent.models import ValidationError


def empty_performance() -> dict[str, Any]:
    """Return explicit unknown effectiveness for an unused knowledge item."""
    return {"basis": "observational_use", "independent_cases": 0,
            "unique_issuers": 0, "evaluated_cases": 0, "evaluated_predictions": 0,
            "technical_cases": 0, "unavailable_cases": 0,
            "disputed_cases": 0,
            "correct_rate": None, "positive_case_correct_rate": None,
            "negative_case_correct_rate": None,
            "paired_cases": 0, "paired_correct_rate_gain": None,
            "confusion_weighting": "one_case_one_weight",
            "confusion": {"tp": 0, "fp": 0, "tn": 0, "fn": 0}}


def use_performance(rows: Iterable[Mapping[str, Any]], item_ref: str) -> dict[str, Any]:
    """Summarize observed-use correctness with independent-case weighting."""
    result = empty_performance()
    cases: dict[str, dict[tuple[Any, ...], Mapping[str, Any]]] = defaultdict(dict)
    all_cases, issuers, technical, unavailable, disputed = set(), set(), set(), set(), set()
    truths: dict[str, bool] = {}
    rows = tuple(rows)
    measurement_states: dict[str, set[tuple[str, str]]] = defaultdict(set)
    if not item_ref.startswith("reflection:"):
        for row in rows:
            if not row["technical"]:
                for observation in row.get("signal_observations", ()):
                    if observation["signal_ref"] == item_ref:
                        measurement_states[observation["input_key"]].add((observation["state"], observation["coverage"]))
    disputed_inputs = {key for key, states in measurement_states.items() if len(states) > 1}
    for row in rows:
        case = row["case_key"]
        if case in truths and truths[case] is not row["actual"]:
            raise ValidationError("knowledge case has conflicting immutable outcomes")
        truths[case] = row["actual"]
        experience = item_ref.startswith("reflection:")
        used = item_ref in (row.get("experience_refs") or ()) if experience else item_ref in row["signal_refs"]
        invalid = not experience and item_ref in row["invalid_signal_refs"]
        if not used and not invalid:
            continue
        all_cases.add(case)
        issuers.add(row["issuer_key"])
        if row["technical"]:
            technical.add(case)
        elif invalid:
            unavailable.add(case)
        elif any(observation["signal_ref"] == item_ref and observation["input_key"] in disputed_inputs
                 for observation in row.get("signal_observations", ())):
            disputed.add(case)
        else:
            # Repeated identical result/context cannot manufacture sample count.
            key = (row["scope_key"], row["input_hash"], row["predicted"])
            cases[case][key] = row
    correct, positive, negative = [], [], []
    for values in cases.values():
        observations = tuple(values.values())
        rate = sum(row["predicted"] == row["actual"] for row in observations) / len(observations)
        correct.append(rate)
        (positive if observations[0]["actual"] else negative).append(rate)
        for row in observations:
            cell = ("tp" if row["predicted"] else "fn") if row["actual"] else ("fp" if row["predicted"] else "tn")
            result["confusion"][cell] += 1 / len(observations)
    result.update(independent_cases=len(all_cases), unique_issuers=len(issuers),
        evaluated_cases=len(cases), evaluated_predictions=sum(len(values) for values in cases.values()),
        technical_cases=len(technical), unavailable_cases=len(unavailable), disputed_cases=len(disputed),
        correct_rate=sum(correct) / len(correct) if correct else None,
        positive_case_correct_rate=sum(positive) / len(positive) if positive else None,
        negative_case_correct_rate=sum(negative) / len(negative) if negative else None)
    return result


def usage_context(value: Mapping[str, Any] | None = None) -> dict[str, Any]:
    """Validate a card's interpretation boundaries without inventing missing prose.

    Example: ``usage_context({"when_to_use": "Demand inflection", ...})``.
    """
    if value is None:
        return {"when_to_use": None, "failure_conditions": [], "related_refs": []}
    if not isinstance(value, Mapping) or set(value) != {
        "when_to_use", "failure_conditions", "related_refs"
    }:
        raise ValidationError("usage_context fields are invalid")
    when = value["when_to_use"]
    if when is not None and (not isinstance(when, str) or not when.strip() or len(when) > 2000):
        raise ValidationError("usage_context when_to_use must be bounded text or null")
    failures = value["failure_conditions"]
    refs = value["related_refs"]
    for name, rows, limit in (("failure_conditions", failures, 8), ("related_refs", refs, 12)):
        if not isinstance(rows, (list, tuple)) or len(rows) > limit or any(
            not isinstance(row, str) or not row.strip() or len(row) > 1000 for row in rows
        ) or len(set(rows)) != len(rows):
            raise ValidationError(f"usage_context {name} must be a bounded unique text array")
    if any(re.fullmatch(r"(?:reflection:[0-9a-f]{64}|[a-z0-9_:-]+:v[1-9][0-9]*)", ref) is None for ref in refs):
        raise ValidationError("usage_context related_refs must be stable knowledge refs")
    return {"when_to_use": when, "failure_conditions": list(failures), "related_refs": list(refs)}


def source_signal_refs(value: Any) -> set[str]:
    """Find explicit exact Signal refs in sourced structured records, never prose."""
    found: set[str] = set()
    if isinstance(value, Mapping):
        ref = value.get("signal_ref")
        if isinstance(ref, str) and re.fullmatch(r"[a-z0-9_:-]+:v[1-9][0-9]*", ref):
            found.add(ref)
        uses = value.get("signal_usage")
        if isinstance(uses, Mapping):
            found.update(ref for ref in uses if isinstance(ref, str) and re.fullmatch(r"[a-z0-9_:-]+:v[1-9][0-9]*", ref))
        related = value.get("related_signal_refs", ())
        if isinstance(related, (list, tuple)):
            found.update(ref for ref in related if isinstance(ref, str) and re.fullmatch(r"[a-z0-9_:-]+:v[1-9][0-9]*", ref))
        for nested in value.values():
            found.update(source_signal_refs(nested))
    elif isinstance(value, (list, tuple)):
        for nested in value:
            found.update(source_signal_refs(nested))
    return found


def knowledge_observations(record: Mapping[str, Any], *, contract_hash: str) -> list[dict[str, Any]]:
    """Derive source-bound use/outcome rows from a canonical committed Plan record."""
    digest = canonical_json_hash(record)
    plan = record["plan"]
    adopted = plan.get("experience_usage")
    menu = record.get("knowledge_signal_refs")
    scope = canonical_json_hash({"contract_hash": contract_hash,
        "snapshots": record.get("dataset_snapshot_ids", []),
        "stage": record.get("evaluation_stage")})
    rows = []
    for position, trajectory in enumerate(record["trajectories"]):
        case = canonical_json_hash({"issuer": trajectory["company_id"], "time": trajectory["prediction_time"]})
        prediction = trajectory["prediction"]
        actual = trajectory["ground_truth"]["is_surge"]
        predicted = prediction["is_surge"]
        if type(actual) is not bool or type(predicted) is not bool:
            raise ValidationError("knowledge observations require canonical binary outcomes")
        signals: set[str] = set()
        invalid: set[str] = set()
        states: dict[str, str] = {}
        observations = []
        for signal_round in trajectory.get("signal_rounds", ()):
            for result in signal_round["batch"]["results"]:
                ref = f"{result['signal_id']}:v{result['version']}"
                status = result.get("execution", {}).get("status", "success")
                state = result["state"]["value"]
                if status in {"success", "domain_unavailable"}:
                    observations.append({"signal_ref": ref,
                        "input_key": canonical_json_hash({"case": case, "ref": ref,
                            "fingerprint": signal_round["batch"].get("document_fingerprints", {}).get(ref, [])}),
                        "state": state, "coverage": result["status"]["coverage"]})
                if status == "success" and state != "unavailable":
                    signals.add(ref)
                    states[ref] = state
                else:
                    invalid.add(ref)
        row = {"record_hash": digest, "position": position,
            "case_key": case, "issuer_key": canonical_json_hash(trajectory["company_id"]),
            "scope_key": scope, "scope_known": bool(contract_hash and record.get("dataset_snapshot_ids")),
            "input_hash": canonical_json_hash(trajectory["final_context"]),
            "experience_refs": list(adopted["item_refs"]) if adopted is not None else None,
            "signal_refs": sorted(signals), "invalid_signal_refs": sorted(invalid - signals),
            "signal_states": states, "signal_menu": menu,
            "signal_observations": observations,
            "actual": actual, "predicted": predicted,
            "technical": str(prediction.get("session_id", "")).startswith("exclusion_")}
        row["event_id"] = canonical_json_hash(row)
        rows.append(row)
    return rows


class KnowledgeUseStore:
    """Rebuildable use observations whose authority is the committed workspace.

    Example: ``KnowledgeUseStore(workspace_root).committed_rows()``.
    """

    def __init__(self, workspace_root: str | Path) -> None:
        self.workspace_root = Path(workspace_root)
        self.root = self.workspace_root / "knowledge"

    def record(self, record: Mapping[str, Any], *, contract_hash: str = "") -> None:
        """Save one derivative; an identical replay repairs its atomic publication."""
        record_hash = canonical_json_hash(record)
        checkpoint_path = self.workspace_root / "experiments" / f"round-{record['round_id']:04d}" / "checkpoint.json"
        if checkpoint_path.exists():
            checkpoint = self._read(checkpoint_path)
            if checkpoint.get("round_id") == record["round_id"] and record["plan_id"] in checkpoint.get("plan_ids", ()):
                contract_hash = str(checkpoint.get("run_contract_hash", ""))
        value = {"schema_version": "knowledge-use-v1", "record_hash": record_hash,
                 "round_id": record["round_id"], "plan_id": record["plan_id"],
                 "contract_hash": contract_hash,
                 "rows": knowledge_observations(record, contract_hash=contract_hash)}
        path = self.root / "observations" / f"{record_hash}.json"
        if path.exists() and self._read(path) != value:
            raise ValidationError("conflicting knowledge observation derivative")
        atomic_write_json(path, value)

    @staticmethod
    def _read(path: Path) -> dict[str, Any]:
        try:
            value = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            raise ValidationError(f"invalid knowledge source: {path.name}") from exc
        if not isinstance(value, dict):
            raise ValidationError("knowledge source must be an object")
        return value

    def committed_rows(self, *, round_cutoff: int | None = None, repair: bool = False) -> tuple[dict[str, Any], ...]:
        """Read only pointer-reachable local derivatives and bound history imports."""
        state_path = self.workspace_root / "state.json"
        state = self._read(state_path) if state_path.exists() else {}
        completed = int(state.get("last_completed_round", 0))
        cutoff = completed if round_cutoff is None else min(completed, round_cutoff)
        if cutoff < 0:
            raise ValidationError("knowledge round cutoff cannot be negative")
        result: dict[str, dict[str, Any]] = {}

        def add(rows: Any) -> None:
            if not isinstance(rows, list):
                raise ValidationError("knowledge observations must be an array")
            for row in rows:
                if not isinstance(row, dict) or not isinstance(row.get("event_id"), str):
                    raise ValidationError("knowledge observation identity is invalid")
                required = {"event_id", "record_hash", "position", "case_key", "issuer_key",
                    "scope_key", "scope_known", "input_hash", "experience_refs", "signal_refs",
                    "invalid_signal_refs", "signal_states", "signal_menu", "signal_observations",
                    "actual", "predicted", "technical"}
                if set(row) != required or any(type(row[name]) is not bool
                        for name in ("scope_known", "actual", "predicted", "technical")):
                    raise ValidationError("knowledge observation shape is invalid")
                if any(not isinstance(row[name], str) or re.fullmatch(r"[0-9a-f]{64}", row[name]) is None
                       for name in ("event_id", "record_hash", "case_key", "issuer_key", "scope_key", "input_hash")):
                    raise ValidationError("knowledge observation hashes are invalid")
                if type(row["position"]) is not int or row["position"] < 0:
                    raise ValidationError("knowledge observation position is invalid")
                for name in ("experience_refs", "signal_refs", "invalid_signal_refs", "signal_menu"):
                    refs = row[name]
                    if refs is None and name in {"experience_refs", "signal_menu"}:
                        continue
                    pattern = r"reflection:[0-9a-f]{64}" if name == "experience_refs" else r"[a-z0-9_:-]+:v[1-9][0-9]*"
                    if not isinstance(refs, list) or any(not isinstance(ref, str) or re.fullmatch(pattern, ref) is None
                                                       for ref in refs) or len(refs) != len(set(refs)):
                        raise ValidationError("knowledge observation references are invalid")
                if not isinstance(row["signal_states"], dict) or not isinstance(row["signal_observations"], list):
                    raise ValidationError("knowledge measurement collection is invalid")
                for observation in row["signal_observations"]:
                    if (not isinstance(observation, dict) or set(observation) != {"signal_ref", "input_key", "state", "coverage"}
                        or any(not isinstance(value, str) for value in observation.values())
                        or re.fullmatch(r"[a-z0-9_:-]+:v[1-9][0-9]*", observation["signal_ref"]) is None
                        or re.fullmatch(r"[0-9a-f]{64}", observation["input_key"]) is None):
                        raise ValidationError("knowledge measurement identity is invalid")
                event_id = row["event_id"]
                if event_id != canonical_json_hash({key: val for key, val in row.items() if key != "event_id"}):
                    raise ValidationError("knowledge observation hash mismatch")
                if event_id in result and result[event_id] != row:
                    raise ValidationError("conflicting knowledge observation identity")
                result[event_id] = row

        for round_id in range(1, cutoff + 1):
            checkpoint = self._read(self.workspace_root / "experiments" / f"round-{round_id:04d}" / "checkpoint.json")
            if checkpoint.get("round_id") != round_id:
                raise ValidationError("knowledge checkpoint identity mismatch")
            for plan_id in checkpoint["plan_ids"]:
                record = self._read(self.workspace_root / "plans" / plan_id / "record.json")
                if record.get("round_id") != round_id or record.get("plan_id") != plan_id:
                    raise ValidationError("knowledge checkpoint record mismatch")
                digest = canonical_json_hash(record)
                path = self.root / "observations" / f"{digest}.json"
                if not path.exists():
                    # Pointer commit may precede derivative publication. Rebuild without model I/O.
                    contract_hash = str(checkpoint.get("run_contract_hash", ""))
                    if repair:
                        self.record(record, contract_hash=contract_hash)
                        value = self._read(path)
                    else:
                        value = {"schema_version": "knowledge-use-v1", "record_hash": digest,
                            "round_id": round_id, "plan_id": plan_id, "contract_hash": contract_hash,
                            "rows": knowledge_observations(record, contract_hash=contract_hash)}
                else:
                    value = self._read(path)
                if (value.get("schema_version") != "knowledge-use-v1"
                    or value.get("record_hash") != digest
                    or value.get("round_id") != round_id or value.get("plan_id") != plan_id
                    or value.get("contract_hash") != str(checkpoint.get("run_contract_hash", ""))):
                    raise ValidationError("knowledge derivative source mismatch")
                if value["rows"] != knowledge_observations(record, contract_hash=value.get("contract_hash", "")):
                    raise ValidationError("knowledge derivative differs from canonical source")
                add(value["rows"])
        contract_path = self.workspace_root / "run_contract.json"
        envelope = self._read(contract_path) if contract_path.exists() else {}
        contract = envelope.get("contract", {})
        if envelope and envelope.get("contract_hash") != canonical_json_hash(contract):
            raise ValidationError("knowledge import contract hash mismatch")
        for kind in ("slow_bootstrap", "slow_history"):
            path = self.workspace_root / kind / "manifest.json"
            if not path.exists():
                continue
            if not contract:
                # Definition materialization precedes frozen-contract publication.
                # An unbound manifest grants no observation visibility.
                continue
            envelope = self._read(path)
            manifest = envelope.get("manifest", {})
            digest = canonical_json_hash(manifest)
            if envelope.get("manifest_hash") != digest or contract.get(kind + "_manifest_hash") != digest:
                raise ValidationError("knowledge import is not authorized by frozen contract")
            add(manifest.get("knowledge_observations", []))
        return tuple(result[key] for key in sorted(result))

    def profiles(self, *, round_cutoff: int | None = None, publish: bool = True) -> dict[str, dict[str, Any]]:
        """Build full-history profiles; model callers disclose only bounded cards."""
        rows = self.committed_rows(round_cutoff=round_cutoff, repair=publish and round_cutoff is None)
        refs = {ref for row in rows for ref in [*(row.get("experience_refs") or ()),
            *row["signal_refs"], *row["invalid_signal_refs"]]}
        profiles = {ref: use_performance(rows, ref) for ref in sorted(refs)}
        if round_cutoff is None and publish:
            atomic_write_json(self.root / "profiles.json", {
                "schema_version": "knowledge-profiles-v1", "source_hash": canonical_json_hash(rows),
                "profiles": profiles})
        return profiles
