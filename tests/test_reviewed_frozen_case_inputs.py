"""Temp-only frozen-cohort tests; never open the actual v182 mixed envelope."""
from copy import deepcopy
import json
from pathlib import Path
import shutil
import sys
from tempfile import TemporaryDirectory
from unittest import TestCase
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import diagnose_reviewed_frozen_case_inputs as diagnostic
from stock_opportunity_agent.artifacts import atomic_write_json, canonical_json_hash
from stock_opportunity_agent.data.raw_info import RawInfoStore
from stock_opportunity_agent.models import ValidationError


def fixture_projection(origin):
    rows, companies = {}, []
    order = ("discovery", "anchor", "evolution_validation")
    for split in order:
        rows[split] = []
        for _ in range(diagnostic.COUNTS[split]):
            index = len(companies) + 1
            cik = str(index).zfill(10)
            company = "cik_" + cik
            companies.append({"company_id": company, "cik": cik, "symbol": "TEMP" + str(index)})
            rows[split].append({"case_id": company + ":20250101", "company_id": company,
                "prediction_time": "2025-01-01T08:00:00+08:00", "basic_info": {"prose": "do not export"},
                "ground_truth": {"fixture_secret": "never read or export"}})
    opaque = "a" * 64
    envelope = {"schema_version": "diagnostic-development-subset-v1", "selection_seed": 42,
        "selection_before_model_calls": True, "approved_manifest_hash": diagnostic.APPROVED_SHA,
        "locked_test_hash": opaque, "splits": rows}
    approved = {"approval_status": "human_approved", "locked_test_sealed": True,
                "artifacts": {"locked_test": {"sha256": opaque}}}
    scope = {"outcome_fields_included": False, "split_ownership_included": False, "companies": companies}
    origin.write_text(json.dumps(envelope))
    projection = diagnostic._project_cases(envelope, scope, approved, diagnostic._stream_binding(origin))
    return envelope, scope, approved, projection


def copy_group(root, name):
    if name == "default_v6":
        source = diagnostic.HISTORY_REGISTRY
        refs = list(diagnostic.DEFAULT_REFS)
        version, expected = 6, diagnostic.DEFAULT_HASH
    else:
        plan = diagnostic._read(diagnostic.PERIODIC_STAGE / "plan.json")
        source = Path(diagnostic._read(plan["registry_source_inputs"]["path"])["registry_root"])
        refs, version, expected = plan["registry_refs"], 12, diagnostic.LATEST_HASH
    destination = root / name
    destination.mkdir()
    shutil.copyfile(source / "registry.json", destination / "registry.json")
    for ref in refs:
        signal, v = ref.rsplit(":v", 1)
        manifest = next(source.glob("*/" + signal + "/manifest.json"))
        relative = manifest.parent.relative_to(source)
        target = destination / relative
        (target / "versions" / ("v" + v)).mkdir(parents=True)
        shutil.copyfile(manifest, target / "manifest.json")
        for filename in ("spec.json", "skill.md"):
            original = manifest.parent / "versions" / ("v" + v) / filename
            if original.exists():
                shutil.copyfile(original, target / "versions" / ("v" + v) / filename)
    return {"name": name,
        "root": str(destination), "version": version, "registry_hash": expected, "refs": refs}


class FrozenCaseInputTests(TestCase):
    def test_source_owner_projection_exact_order_and_strict_whitelist(self):
        with TemporaryDirectory() as directory:
            envelope, scope, approved, projection = fixture_projection(Path(directory) / "origin.json")
            self.assertEqual(projection["split_order"], list(envelope["splits"]))
            expected = [(split, i, row["case_id"], row["company_id"], row["prediction_time"])
                for split, rows in envelope["splits"].items() for i, row in enumerate(rows)]
            actual = [(row["split"], row["split_case_index"], row["case_id"], row["company_id"], row["prediction_time"])
                for row in projection["cases"]]
            self.assertEqual(actual, expected)
            self.assertEqual([row["order"] for row in projection["cases"]], list(range(40)))
            payload = json.dumps(projection)
            for forbidden in ("ground_truth", "basic_info", "prose", "fixture_secret", "never read or export"):
                self.assertNotIn(forbidden, payload)
            projection["cases"][0]["basic_info"] = {}
            with self.assertRaisesRegex(diagnostic.ReviewedSourceRejected, "unsupported fields"):
                diagnostic._validate_projection(projection)

    def test_projection_rejects_bad_identity_counts_time_and_scope_without_filtering(self):
        with TemporaryDirectory() as directory:
            envelope, scope, approved, projection = fixture_projection(Path(directory) / "origin.json")
            for mode in ("duplicate", "naive", "count", "missing_identity", "wrong_cik", "seed_bool"):
                changed, identities = deepcopy(envelope), deepcopy(scope)
                first = changed["splits"]["discovery"][0]
                if mode == "duplicate":
                    changed["splits"]["discovery"][1]["case_id"] = first["case_id"]
                elif mode == "naive":
                    first["prediction_time"] = "2025-01-01T00:00:00"
                elif mode == "count":
                    changed["splits"]["anchor"].pop()
                elif mode == "missing_identity":
                    identities["companies"].pop(0)
                elif mode == "wrong_cik":
                    identities["companies"][0]["cik"] = "0000999999"
                else:
                    changed["selection_seed"] = True
                with self.subTest(mode=mode), self.assertRaises(diagnostic.ReviewedSourceRejected):
                    diagnostic._project_cases(changed, identities, approved, projection["origin"])

    def test_definition_only_exact_snapshots_and_unknown_version_reject(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            for name in ("default_v6", "latest_v12"):
                group = copy_group(root, name)
                value, bindings = diagnostic._snapshot(group, root / "output")
                self.assertEqual(value.registry_hash, group["registry_hash"])
                self.assertEqual([s.ref for s in value.specs], group["refs"])
                self.assertFalse(value.learned_profiles)
                self.assertGreater(len(bindings), 18)
                with self.assertRaisesRegex(diagnostic.ReviewedSourceRejected, "overlaps"):
                    diagnostic._snapshot(group, Path(group["root"]) / "new-output")
                bad = {**group, "version": 999}
                with patch.object(diagnostic, "SignalRegistry") as registry:
                    with self.assertRaisesRegex(diagnostic.ReviewedSourceRejected, "version/hash/ref"):
                        diagnostic._snapshot(bad, root / "output")
                    registry.assert_not_called()
                bad = {**group, "refs": [group["refs"][0].rsplit(":v", 1)[0] + ":v999", *group["refs"][1:]]}
                with self.assertRaises((diagnostic.ReviewedSourceRejected, ValidationError)):
                    diagnostic._snapshot(bad, root / "output")

    def test_execute_streams_origin_only_and_preserves_missing_source_40x18_twice(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            origin = root / "mixed-origin.json"
            _envelope, _scope, _approved, projection = fixture_projection(origin)
            output, old = root / "stage", root / "old"
            output.mkdir(); old.mkdir()
            groups = [copy_group(root, name) for name in ("default_v6", "latest_v12")]
            for group in groups:
                _snapshot, group["definition_bindings"] = diagnostic._snapshot(group, output)
            path = output / "case-identities.json"
            atomic_write_json(path, projection)
            plan = {"schema_version": "frozen40-source-input-plan-v1", "origin": diagnostic._stream_binding(origin),
                "projection": diagnostic._binding(path), "metadata_authorities": [], "source_bindings": [],
                "old_periodic_tree": [], "code_bindings": [], "groups": groups,
                "fixed_case_denominator": 40, "per_group_resolution_denominator": 720,
                "default_basic_info_case_denominator": 40, "reviewed_source_snapshot": {"root": str(root / "unused-view")},
                **{key: False for key in ("network_allowed", "model_allowed", "labels_allowed", "signal_apply_allowed",
                    "full_prepare_allowed", "global_writes_allowed")}}
            plan["plan_hash"] = canonical_json_hash(plan)
            atomic_write_json(output / "plan.json", plan)
            real_read = diagnostic._read
            def checked_read(path):
                self.assertNotEqual(Path(path).resolve(), origin.resolve(), "execute must never deserialize mixed origin")
                return real_read(path)
            # Real in-memory RawInfoStore/resolver/executors on an empty temp
            # source set. This deliberately tests missing-source preservation,
            # not the actual reviewed653-source qualification or cohort export.
            empty = RawInfoStore(documents=())
            with patch.object(diagnostic, "PERIODIC_STAGE", old), patch.object(diagnostic, "ORIGIN", origin), \
                    patch.object(diagnostic, "ORIGIN_SHA", diagnostic._stream_binding(origin)["sha256"]), \
                    patch.object(diagnostic, "_read", side_effect=checked_read), \
                    patch.object(diagnostic, "open_raw_info_store", return_value=empty):
                result = diagnostic.execute(output)
                self.assertEqual(result["fixed_case_denominator"], 40)
                self.assertEqual(len(list((output / "basic-info").glob("*.json"))), 40)
                for name in ("default_v6", "latest_v12"):
                    self.assertEqual(len(result["groups"][name]["cases"]), 40)
                    self.assertEqual(result["groups"][name]["resolved_count"], 0)
                    paths = list((output / name / "cases").glob("*.json"))
                    self.assertEqual(len(paths), 40)
                    self.assertEqual(sum(len(real_read(p)["exact_signal_input_resolutions"]) for p in paths), 720)
                self.assertTrue(result["mixed_origin_bytes_accessed_for_hash"])
                self.assertFalse(result["mixed_origin_deserialized_during_execute"])
                with self.assertRaises(FileExistsError):
                    diagnostic.execute(output)
                origin.write_bytes(origin.read_bytes() + b' ')
                with self.assertRaisesRegex(diagnostic.ReviewedSourceRejected, "mixed origin bytes changed"):
                    diagnostic._verify_plan(output)

    def test_all_label_store_readers_are_guarded_and_restored(self):
        names = ("load", "ground_truth", "record", "keys", "label_contract", "__len__")
        originals = {name: getattr(diagnostic.LabelStore, name) for name in names}
        with diagnostic._source_only():
            for name in names:
                with self.subTest(name=name), self.assertRaises(diagnostic.ReviewedSourceRejected):
                    getattr(diagnostic.LabelStore, name)()
        for name in names:
            self.assertEqual(getattr(diagnostic.LabelStore, name), originals[name])
