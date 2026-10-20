"""Bounded group wrapper/read-boundary addendum; no prepare or execute."""
import ast
from copy import deepcopy
import hashlib
import importlib.util
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

BASE = Path(__file__).resolve().parents[1]
CURRENT = BASE / "native/run_native.py"
OLD = BASE / "native/run-native-original-group-wrapper.py.txt"


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


assert digest(CURRENT) == "2bb3d312545a859b91acd9f1286ce5c7cdf18ce09ebe7e68928df5885d131124"
assert digest(OLD) == "5ebe26fa354cdeb7057e5c95556b61c5aaab419686e34cc080a705bac141b9e8"


def load(path, name):
    spec = importlib.util.spec_from_loader(name, loader=None)
    module = importlib.util.module_from_spec(spec)
    module.__file__ = str(CURRENT)  # Preserve exact production relative authority paths.
    exec(compile(Path(path).read_text(), str(path), "exec"), module.__dict__)
    return module


old, current = load(OLD, "group_original"), load(CURRENT, "group_current")
old_ast, new_ast = ast.parse(OLD.read_text()), ast.parse(CURRENT.read_text())
for tree in (old_ast, new_ast):
    tree.body = [node for node in tree.body if not isinstance(node, ast.FunctionDef)
                 or node.name not in ("verify_group_identity", "authorities")]
assert ast.dump(old_ast, include_attributes=False) == ast.dump(new_ast, include_attributes=False)
stage_present = current.OUTPUT.exists()  # Sole executor may prepare concurrently; do not inspect it.
blocked = AssertionError("No stage/Signal/Store operation permitted")
with patch.object(old, "open_raw_info_store", side_effect=blocked), patch.object(old.SignalExecutor, "execute_batch", side_effect=blocked):
    try:
        old.authorities()
    except ValueError as error:
        assert str(error) == "exact original latest_v12 group differs"
    else:
        raise AssertionError("original full-wrapper equality did not reject")
oracle_group = current.read(BASE / "oracle/definitions.json")["group"]
original = next(g for g in current.read(current.INPUTS / "plan.json")["groups"] if g["name"] == "latest_v12")
assert len(oracle_group) == 5 and len(original["definition_bindings"]) == 43
actual = current.verify_group_identity(oracle_group, original)
assert actual == original["definition_bindings"]
negative_count = 0
with TemporaryDirectory() as temporary:
    path = Path(temporary) / "definition.json"
    path.write_text('{"unchanged":true}\n')
    group = {"name": "latest_v12", "refs": ["a:v1", "b:v2"], "root": "/synthetic-only",
             "version": 12, "registry_hash": "a" * 64}
    wrapper = {**group, "definition_bindings": [current.binding(path)]}
    assert current.verify_group_identity(group, wrapper) == wrapper["definition_bindings"]
    for key, value in (("name", "other"), ("refs", list(reversed(group["refs"]))),
                       ("registry_hash", "b" * 64), ("root", "/other"),
                       ("version", 12.0), ("version", True)):
        changed = {**group, key: value}
        try:
            current.verify_group_identity(changed, wrapper)
        except ValueError as error:
            assert "identity differs" in str(error)
            negative_count += 1
        else:
            raise AssertionError((key, value))
    bad = deepcopy(wrapper)
    bad["definition_bindings"][0]["sha256"] = "0" * 64
    try:
        current.verify_group_identity(group, bad)
    except ValueError as error:
        assert "frozen file differs" in str(error)
        negative_count += 1
    else:
        raise AssertionError("definition proof SHA was not checked")
assert current.OUTPUT.exists() == stage_present
report = {"status": "PASS_group_wrapper_boundary_addendum", "runner_sha256": digest(CURRENT),
          "controls_sha256": digest(BASE / "native/safety_controls.py"),
          "old_runner_sha256": digest(OLD), "actual_identity_fields_equal": 5,
          "actual_historical_definition_bindings_verified": 43,
          "temporary_positive": True, "temporary_single_variable_rejections": negative_count,
          "unchanged_other_runner_AST": True, "formal_stage_exists": stage_present,
          "formal_stage_access": "Existence only; executor may prepare independently. No stage file read or mutation.",
          "original_failure": "Actual prepare failed before writes; old authorities reproduced its group-wrapper mismatch. No Signal/data/model failure.",
          "earlier_review_limit": "Earlier PASS covered guards/comparison/restore but missed actual oracle-vs-oldplan wrapper shape. It did not establish real prepare success; prior evidence is retained unchanged.",
          "remaining": "Current authorities whole4136-source freeze was read-only checked by driver, not repeated here. Sole actual prepare/plan and execution remain independently authorized steps."}
target = BASE / "independent/group-wrapper-review.json"
target.write_text(json.dumps(report, indent=2) + "\n")
print(json.dumps({"status": report["status"], "review_sha256": digest(target), "negative_count": negative_count}))
