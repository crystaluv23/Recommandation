"""Snapshot-bound incremental state updates and typed correction operations."""

from __future__ import annotations

from copy import deepcopy
import hashlib
import json
import re
from typing import Any, Iterable, Mapping

from stock_opportunity_agent.models import ValidationError


PATCH_SCHEMA = "structured-state-patch-v1"
PATCH_INSTRUCTION = (
    " When output_patch_contract is supplied, return exactly "
    '{"base_hash":"the issued base_hash","operations":[...]}. '
    "Return changes only, never the full object or unchanged siblings. "
    "Each operation has op and path; replace/add/append also have value. "
    "Use only issued permissions. All indices address the same base snapshot, "
    "not a progressively shortened list. replace changes one value, remove "
    "deletes one authorized member, add creates a missing dictionary key, and "
    "append adds one new list member. Do not replace a whole existing list. "
    "Omitted fields are preserved by the runtime. The merged full object must "
    "still satisfy every original contract and validation obligation."
)


def state_patch_hash(value: Mapping[str, Any]) -> str:
    """Identify the exact JSON snapshot whose indices a patch may address."""

    try:
        encoded = json.dumps(
            dict(value), ensure_ascii=False, sort_keys=True, separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise ValidationError("patch snapshot must contain only finite JSON values") from exc
    return hashlib.sha256(encoded).hexdigest()


def _tokens(path: str) -> tuple[str | int, ...]:
    if not isinstance(path, str) or re.fullmatch(
        r"[A-Za-z_][A-Za-z0-9_]*(?:\.[A-Za-z_][A-Za-z0-9_]*|\[(?:0|[1-9]\d*)\])*", path
    ) is None:
        raise ValidationError("patch path must use exact field/member indices")
    return tuple(
        int(value[1:-1]) if value.startswith("[") else value
        for value in re.findall(r"[A-Za-z_][A-Za-z0-9_]*|\[\d+\]", path)
    )


def _path(tokens: Iterable[str | int]) -> str:
    value = ""
    for token in tokens:
        value += f"[{token}]" if isinstance(token, int) else ("." if value else "") + token
    return value


def _lookup(base: Any, tokens: tuple[str | int, ...]) -> Any:
    value = base
    for token in tokens:
        if isinstance(token, int):
            if not isinstance(value, list) or token >= len(value):
                raise ValidationError(f"patch path does not exist: {_path(tokens)}")
        elif not isinstance(value, Mapping) or token not in value:
            raise ValidationError(f"patch path does not exist: {_path(tokens)}")
        value = value[token]
    return value


def _exists(base: Mapping[str, Any], tokens: tuple[str | int, ...]) -> bool:
    try:
        _lookup(base, tokens)
    except ValidationError:
        return False
    return True


def state_patch_contract(
    base: Mapping[str, Any],
    *,
    mode: str = "state",
    obligations: Iterable[Mapping[str, Any]] = (),
) -> dict[str, Any]:
    """Describe allowed operations without deriving authority from error prose.

    ``mode='state'`` exposes individual ResearchState members. Correction mode
    requires the owning validator's typed obligations, not a free-text error.
    """

    permissions: list[dict[str, Any]] = []
    append_limits: dict[str, int] = {}
    exact_append_limits: dict[str, dict[str, int]] = {}
    guards: list[dict[str, Any]] = []

    def permit(op: str, path: str, *, descendants: bool = False, invalid_container: bool = False) -> None:
        _tokens(path)
        row = {"op": op, "path": path, "descendants": descendants}
        if invalid_container:
            row["invalid_container"] = True
        if row not in permissions:
            permissions.append(row)

    def permit_path(path: str, repairs: set[str]) -> None:
        tokens = _tokens(path)
        if not _exists(base, tokens):
            if "add" in repairs and isinstance(tokens[-1], str):
                parent = _lookup(base, tokens[:-1])
                if isinstance(parent, Mapping):
                    permit("add", path)
            return
        value = _lookup(base, tokens)
        if isinstance(value, list):
            # A collection-level issue can repair existing members, but never
            # turn a narrow repair into wholesale membership replacement.
            for index, row in enumerate(value):
                item_path = f"{path}[{index}]"
                if "replace" in repairs:
                    permit("replace", item_path, descendants=isinstance(row, Mapping))
                if "remove" in repairs or "quarantine" in repairs:
                    permit("remove", item_path)
        else:
            if "replace" in repairs:
                permit("replace", path, descendants=isinstance(value, Mapping))
            if "remove" in repairs or "quarantine" in repairs:
                permit("remove", path)

    if mode == "state":
        fields = {
            "hypotheses", "current_beliefs", "supporting_evidence", "contradictions",
            "resolved_questions", "open_questions", "next_information_needs", "decision",
        }
        if set(base) != fields:
            raise ValidationError("state patch requires the complete ResearchState snapshot")
        for name, value in base.items():
            if name == "decision":
                permit("replace", name)
            elif isinstance(value, list):
                permit_path(name, {"replace", "remove"})
                permit("append", name)
            else:
                raise ValidationError("ResearchState patch collections must be arrays")
    elif mode == "correction":
        for raw in obligations:
            issue = dict(raw)
            if not issue.get("issue_code"):
                continue
            repairs = set(issue.get("allowed_repairs", ()))
            paths = tuple(dict.fromkeys((
                *issue.get("must_change_paths", ()),
                *issue.get("must_change_any_of_paths", ()),
                *issue.get("permitted_dependency_paths", ()),
            )))
            if issue.get("required_action") == "restore_exactly" or (
                issue.get("required_action") == "replace_with_exact_residual"
                and issue.get("returned_path") is None
            ):
                # These are prior-state coordinates, not writable returned slots.
                required = issue.get("required_need")
                if isinstance(required, str) and isinstance(base.get("next_information_needs"), list):
                    needed = max(1, int(issue.get("required_need_occurrences", 1)))
                    missing = max(0, needed - base["next_information_needs"].count(required))
                    if missing:
                        permission = {"op": "append", "path": "next_information_needs",
                                      "descendants": False, "exact_value": required}
                        if permission not in permissions:
                            permissions.append(permission)
                        limits = exact_append_limits.setdefault("next_information_needs", {})
                        limits[required] = max(limits.get(required, 0), missing)
                continue
            compaction = type(issue.get("minimum_removed_items")) is int
            issue_append_paths: set[str] = set()
            for path in (() if compaction else paths):
                path_repairs = (
                    set(issue.get("dependency_allowed_repairs", {}).get(path, repairs))
                    if path in issue.get("permitted_dependency_paths", ()) else repairs
                )
                if path in issue.get("invalid_container_paths", ()) and _exists(base, _tokens(path)):
                    for op in ("replace", "remove"):
                        if op in path_repairs:
                            permit(op, path, invalid_container=True)
                else:
                    permit_path(path, path_repairs)
                if issue.get("item_id") is not None and path not in issue.get("permitted_dependency_paths", ()):
                    tokens = _tokens(path)
                    indexed = [i for i, token in enumerate(tokens) if isinstance(token, int)]
                    if indexed:
                        row_tokens = next((
                            tokens[:index + 1] for index in reversed(indexed)
                            if isinstance(_lookup(base, tokens[:index + 1]), Mapping)
                            and issue["item_id_field"] in _lookup(base, tokens[:index + 1])
                        ), tokens[:indexed[0] + 1])
                        row_path = _path(row_tokens)
                        guard = {"path": row_path, "field": issue["item_id_field"],
                                 "value": issue["item_id"]}
                        if guard not in guards:
                            guards.append(guard)
                if "add" in path_repairs and _exists(base, _tokens(path)) and isinstance(_lookup(base, _tokens(path)), list):
                    permit("append", path)
                    issue_append_paths.add(path)
            for path in issue.get("permitted_append_paths", ()):
                if "add" in repairs and isinstance(_lookup(base, _tokens(path)), list):
                    permit("append", path)
                    issue_append_paths.add(path)
            for array_path in issue_append_paths:
                append_limits[array_path] = append_limits.get(array_path, 0) + max(
                    1, len(issue.get("missing_quantity_literals", ()))
                )
            for path in (
                *issue.get("authorized_member_removals", ()),
                *issue.get("required_compaction_remove_paths", ()),
            ):
                if "remove" in repairs or "quarantine" in repairs:
                    permit("remove", path)
    else:
        raise ValidationError("unknown state patch mode")
    return {
        "schema_version": PATCH_SCHEMA,
        "base_hash": state_patch_hash(base),
        "allowed_operations": permissions,
        "append_limits": append_limits,
        "exact_append_limits": exact_append_limits,
        "identity_guards": guards,
        "index_semantics": "all indices address the issued base snapshot",
    }


def apply_state_patch(
    base: Mapping[str, Any], patch: Mapping[str, Any], *, contract: Mapping[str, Any]
) -> dict[str, Any]:
    """Apply one atomic, authorized delta; whole-state semantic validation follows."""

    if set(patch) != {"base_hash", "operations"}:
        raise ValidationError("return a delta with exactly base_hash and operations; not a full object")
    if contract.get("schema_version") != PATCH_SCHEMA or (
        patch["base_hash"] != contract.get("base_hash")
        or patch["base_hash"] != state_patch_hash(base)
    ):
        raise ValidationError("patch base_hash does not match the issued snapshot")
    operations = patch["operations"]
    if not isinstance(operations, list):
        raise ValidationError("patch operations must be an array")
    for guard in contract.get("identity_guards", ()):
        row = _lookup(base, _tokens(guard["path"]))
        if not isinstance(row, Mapping) or row.get(guard["field"]) != guard["value"]:
            raise ValidationError("patch obligation identity differs from the base row")
    edits: list[tuple[str, tuple[str | int, ...], Mapping[str, Any]]] = []
    append_counts: dict[str, int] = {}
    exact_append_counts: dict[tuple[str, str], int] = {}
    for raw in operations:
        if not isinstance(raw, Mapping):
            raise ValidationError("patch operations must be objects")
        op = raw.get("op")
        required = {"op", "path"} if op == "remove" else {"op", "path", "value"}
        if op not in {"replace", "remove", "add", "append"} or set(raw) != required:
            raise ValidationError("patch operation has an invalid shape")
        path = raw["path"]
        tokens = _tokens(path)
        authorized = False
        invalid_container = False
        for permission in contract.get("allowed_operations", ()):
            if permission["op"] != op:
                continue
            prefix = _tokens(permission["path"])
            if tokens == prefix or (permission.get("descendants") and tokens[:len(prefix)] == prefix):
                if "exact_value" not in permission or raw.get("value") == permission["exact_value"]:
                    authorized = True
                    invalid_container = bool(permission.get("invalid_container")) and tokens == prefix
                    break
        if not authorized:
            raise ValidationError(f"patch operation is outside typed authority: {op} {path}")
        if op == "add":
            parent = _lookup(base, tokens[:-1])
            if not isinstance(tokens[-1], str) or not isinstance(parent, Mapping) or tokens[-1] in parent:
                raise ValidationError("add requires an absent dictionary field")
        else:
            old = _lookup(base, tokens)
            if op == "append":
                if not isinstance(old, list):
                    raise ValidationError("append requires an existing list")
                append_counts[path] = append_counts.get(path, 0) + 1
                limit = contract.get("append_limits", {}).get(path)
                if limit is not None and append_counts[path] > limit:
                    raise ValidationError("patch exceeds the authorized append budget")
                if isinstance(raw["value"], str):
                    limit = contract.get("exact_append_limits", {}).get(path, {}).get(raw["value"])
                    if limit is not None:
                        key = (path, raw["value"])
                        exact_append_counts[key] = exact_append_counts.get(key, 0) + 1
                        if exact_append_counts[key] > limit:
                            raise ValidationError("patch exceeds the required literal occurrence count")
            elif op == "replace" and isinstance(old, list) and not invalid_container:
                raise ValidationError("replace individual list members, not the complete list")
        for prior_op, prior_tokens, _ in edits:
            if op == prior_op == "append" and tokens == prior_tokens:
                continue
            # Appending to a list and editing its old members are independent.
            if op == "append" and prior_tokens[:len(tokens)] == tokens and len(prior_tokens) > len(tokens):
                continue
            if prior_op == "append" and tokens[:len(prior_tokens)] == prior_tokens and len(tokens) > len(prior_tokens):
                continue
            if tokens[:len(prior_tokens)] == prior_tokens or prior_tokens[:len(tokens)] == tokens:
                raise ValidationError("patch operations overlap or repeat a write")
        edits.append((op, tokens, raw))
    result = deepcopy(dict(base))
    # Resolve every coordinate before deletion can shift a sibling's index.
    resolved = [(op, _lookup(result, tokens[:-1]), tokens[-1], raw)
                for op, tokens, raw in edits]
    for op, parent, key, raw in resolved:
        if op in {"replace", "add"}:
            parent[key] = deepcopy(raw["value"])
    removals = [row for row in resolved if row[0] == "remove"]
    for _, parent, key, _ in sorted(removals, key=lambda row: row[2] if isinstance(row[2], int) else -1, reverse=True):
        del parent[key]
    for op, parent, key, raw in resolved:
        if op == "append":
            parent[key].append(deepcopy(raw["value"]))
    return result


def recorded_response_patch(base: Mapping[str, Any], response: Mapping[str, Any]) -> dict[str, Any]:
    """Convert a historical complete response for explicitly offline fixture replay.

    This does not validate authority or provide evidence of live patch quality.
    The production patch consumer must still enforce its issued permissions.
    """

    operations: list[dict[str, Any]] = []

    def visit(old: Any, new: Any, path: str) -> None:
        if old == new:
            return
        if isinstance(old, Mapping) and isinstance(new, Mapping):
            for key in old:
                child = f"{path}.{key}" if path else str(key)
                if key not in new:
                    operations.append({"op": "remove", "path": child})
                else:
                    visit(old[key], new[key], child)
            for key in new:
                if key not in old:
                    operations.append({"op": "add", "path": f"{path}.{key}" if path else str(key), "value": new[key]})
        elif isinstance(old, list) and isinstance(new, list):
            # Recorded fixtures needing deletion use exact unchanged subsequence
            # anchors. Ambiguous duplicates require an explicit test-authored delta.
            if len(new) < len(old):
                if any(old.count(row) > 1 for row in old):
                    raise ValidationError("ambiguous recorded list deletion requires an explicit delta")
                kept = 0
                for index, value in enumerate(old):
                    if kept < len(new) and value == new[kept]:
                        kept += 1
                    else:
                        operations.append({"op": "remove", "path": f"{path}[{index}]"})
                if kept != len(new):
                    raise ValidationError("recorded replacement plus deletion requires an explicit delta")
            else:
                for index, value in enumerate(old):
                    visit(value, new[index], f"{path}[{index}]")
                for value in new[len(old):]:
                    operations.append({"op": "append", "path": path, "value": value})
        else:
            operations.append({"op": "replace", "path": path, "value": new})

    visit(dict(base), dict(response), "")
    return {"base_hash": state_patch_hash(base), "operations": operations}
