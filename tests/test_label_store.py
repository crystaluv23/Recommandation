from __future__ import annotations

import json
import tempfile
import unittest
from datetime import date, timedelta
from pathlib import Path

from stock_opportunity_agent.cases.label_store import (
    LabelRecord,
    LabelStore,
    UnknownLabelError,
    build_label_records,
    file_sha256,
    parse_case_key,
    write_label_store,
)
from stock_opportunity_agent.cases.outcomes import SURGE_LABEL_CONTRACT, six_month_smoothed_multiple
from stock_opportunity_agent.models import ValidationError


def _bars(as_of: date, *, pre: int = 6, post: int = 190, peak_from=100) -> list[dict]:
    rows: list[dict] = []
    for offset in range(-pre, 0):
        rows.append({
            "as_of_date": (as_of + timedelta(days=offset)).isoformat(),
            "adjusted_close": 100.0,
        })
    for offset in range(0, post):
        value = 220.0 if 100 <= offset <= 104 else float(peak_from)
        rows.append({
            "as_of_date": (as_of + timedelta(days=offset)).isoformat(),
            "adjusted_close": value,
        })
    return rows


class LabelStoreTests(unittest.TestCase):
    AS_OF = date(2025, 1, 15)

    def _build_store(self) -> tuple[Path, LabelRecord]:
        bars = _bars(self.AS_OF)
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        base = Path(temporary.name)
        archive = base / "price_histories.json"
        archive.write_text(json.dumps({
            "schema_version": "scheme-evolution-adjusted-prices-v1",
            "source": "offline-label-store-test-fixture",
            "start_date": bars[0]["as_of_date"], "end_date": bars[-1]["as_of_date"],
            "requested_symbol_count": 2, "priced_symbol_count": 2, "failed_symbols": {},
            "bars_by_symbol": {"DEMO": bars, "OTHER": [
                {**bar, "adjusted_close": bar["adjusted_close"] * 3} for bar in bars]},
        }), encoding="utf-8")
        records, exclusions = build_label_records(
            {"DEMO": bars},
            [("cik_00000001", self.AS_OF.isoformat())],
            {"cik_00000001": "DEMO"},
        )
        self.assertEqual(exclusions, [])
        self.assertEqual(len(records), 1)
        root = base / "outcome-label-store-v1"
        write_label_store(
            root,
            records=records,
            archive_path=archive,
            archive_sha256=file_sha256(archive),
            created_at="2026-10-01T00:00:00+00:00",
        )
        return root, records[0]

    def _manifest(self, root: Path) -> dict:
        return json.loads((root / "manifest.json").read_text())

    def _write_manifest(self, root: Path, manifest: dict) -> None:
        (root / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")

    def _write_record(self, root: Path, record: dict) -> None:
        (root / "labels.jsonl").write_text(json.dumps(record) + "\n", encoding="utf-8")

    def _rewrite_archive(self, root: Path, payload) -> None:
        manifest = self._manifest(root)
        archive = Path(manifest["archive_path"])
        archive.write_text(json.dumps(payload), encoding="utf-8")
        manifest["archive_sha256"] = file_sha256(archive)
        self._write_manifest(root, manifest)

    def test_round_trip_matches_shared_calculator(self) -> None:
        root, record = self._build_store()
        store = LabelStore.load(root)
        self.assertEqual(len(store), 1)
        truth = store.ground_truth("cik_00000001", self.AS_OF)
        expected = six_month_smoothed_multiple(_bars(self.AS_OF), self.AS_OF)
        self.assertEqual(
            truth["realized_max_multiple"], expected["realized_max_multiple"]
        )
        self.assertEqual(truth["is_surge"], expected["is_surge"])
        self.assertEqual(truth["magnitude"], expected["magnitude"])
        self.assertEqual(store.record("cik_00000001", self.AS_OF), record)
        self.assertEqual(store.keys(), (("cik_00000001", self.AS_OF.isoformat()),))
        self.assertEqual(store.label_contract(), SURGE_LABEL_CONTRACT)
        before = {path: path.read_bytes() for path in (root / "manifest.json", root / "labels.jsonl",
                                                      Path(self._manifest(root)["archive_path"]))}
        self.assertEqual(LabelStore.load(root).record("cik_00000001", self.AS_OF).to_dict(), record.to_dict())
        self.assertEqual(before, {path: path.read_bytes() for path in before})

    def test_unknown_key_fails_closed_with_near_keys(self) -> None:
        root, _ = self._build_store()
        store = LabelStore.load(root)
        with self.assertRaises(UnknownLabelError) as raised:
            store.ground_truth("cik_00000001", "2025-06-30")
        self.assertIn("no label for", str(raised.exception))
        self.assertIn("cik_00000001", str(raised.exception))

    def test_duplicate_keys_are_rejected(self) -> None:
        root, record = self._build_store()
        lines = (root / "labels.jsonl").read_text().splitlines()
        (root / "labels.jsonl").write_text(
            "\n".join([*lines, lines[-1]]) + "\n", encoding="utf-8"
        )
        with self.assertRaisesRegex(ValidationError, "duplicate label key"):
            LabelStore.load(root)

    def test_manifest_record_count_mismatch_is_rejected(self) -> None:
        root, _ = self._build_store()
        manifest = json.loads((root / "manifest.json").read_text())
        manifest["record_count"] = 5
        (root / "manifest.json").write_text(json.dumps(manifest))
        with self.assertRaisesRegex(ValidationError, "manifest declares"):
            LabelStore.load(root)

    def test_schema_violations_are_rejected(self) -> None:
        _root, record = self._build_store()
        base = record.to_dict()
        LabelRecord.from_dict(base)
        wrong_magnitude = next(value for value in SURGE_LABEL_CONTRACT["magnitude_classes"]
                               if value != base["magnitude"])
        for mutation, message in (
            ({"magnitude": wrong_magnitude}, "magnitude disagrees"),
            ({"is_surge": not base["is_surge"]}, "is_surge disagrees"),
            ({"realized_max_multiple": 0.0}, "finite and positive"),
        ):
            with self.subTest(mutation=mutation):
                with self.assertRaisesRegex(ValidationError, message):
                    LabelRecord.from_dict({**base, **mutation})
        missing = {key: value for key, value in base.items() if key != "symbol"}
        with self.assertRaisesRegex(ValidationError, "missing fields"):
            LabelRecord.from_dict(missing)

    def test_missing_wrong_or_changed_archive_is_rejected(self) -> None:
        for variant in ("missing", "directory", "wrong_hash", "changed_bytes", "malformed_bound_json"):
            with self.subTest(variant=variant):
                root, _record = self._build_store()
                manifest = self._manifest(root)
                archive = Path(manifest["archive_path"])
                if variant == "missing":
                    archive.unlink()
                elif variant == "directory":
                    manifest["archive_path"] = str(archive.parent)
                    self._write_manifest(root, manifest)
                elif variant == "wrong_hash":
                    manifest["archive_sha256"] = "f" * 64
                    self._write_manifest(root, manifest)
                elif variant == "changed_bytes":
                    archive.write_text(archive.read_text() + "\n")
                else:
                    archive.write_text("{not-json")
                    manifest["archive_sha256"] = file_sha256(archive)
                    self._write_manifest(root, manifest)
                with self.assertRaises(ValidationError):
                    LabelStore.load(root)

    def test_calculator_and_label_contract_must_match_exactly(self) -> None:
        for variant in ("calculator", "threshold", "horizon", "missing_contract_field", "extra_contract_field"):
            with self.subTest(variant=variant):
                root, _record = self._build_store()
                manifest = self._manifest(root)
                if variant == "calculator":
                    manifest["calculator"] += "_unreviewed"
                elif variant == "threshold":
                    manifest["label_contract"]["binary_threshold"] += 1
                elif variant == "horizon":
                    manifest["label_contract"]["horizon"] = "three_calendar_months"
                elif variant == "missing_contract_field":
                    manifest["label_contract"].pop("baseline")
                else:
                    manifest["label_contract"]["unreviewed_policy"] = True
                self._write_manifest(root, manifest)
                with self.assertRaises(ValidationError):
                    LabelStore.load(root)

    def test_internally_consistent_record_is_recomputed_from_bound_archive(self) -> None:
        for variant in ("scaled_raw_means", "different_calculated_outcome"):
            with self.subTest(variant=variant):
                root, record = self._build_store()
                changed = record.to_dict()
                if variant == "scaled_raw_means":
                    changed["baseline_mean"] *= 2
                    changed["future_peak_mean"] *= 2
                else:
                    different_bars = [{**bar, "adjusted_close": bar["adjusted_close"] *
                                       (3 if bar["as_of_date"] >= self.AS_OF.isoformat() else 1)}
                                      for bar in _bars(self.AS_OF)]
                    changed.update(six_month_smoothed_multiple(different_bars, self.AS_OF))
                # Both variants satisfy internal threshold/magnitude rules;
                # only the bound original archive can reject their provenance.
                LabelRecord.from_dict(changed)
                self._write_record(root, changed)
                with self.assertRaises(ValidationError):
                    LabelStore.load(root)

    def test_every_observation_date_boundary_and_symbol_is_recomputed(self) -> None:
        for variant in ("baseline_dates", "future_peak_dates", "horizon_end", "as_of_date", "missing_symbol", "wrong_existing_symbol"):
            with self.subTest(variant=variant):
                root, record = self._build_store()
                changed = record.to_dict()
                if variant in {"baseline_dates", "future_peak_dates"}:
                    changed[variant] = [(date.fromisoformat(value) - timedelta(days=1)).isoformat()
                                        for value in changed[variant]]
                elif variant in {"horizon_end", "as_of_date"}:
                    changed[variant] = (date.fromisoformat(changed[variant]) + timedelta(days=1)).isoformat()
                else:
                    changed["symbol"] = "MISSING" if variant == "missing_symbol" else "OTHER"
                self._write_record(root, changed)
                with self.assertRaises(ValidationError):
                    LabelStore.load(root)

    def test_record_numeric_and_boolean_fields_reject_type_coercion(self) -> None:
        for field in ("baseline_mean", "future_peak_mean", "realized_max_multiple"):
            for invalid in (True, False, "1.0", None, [], {}, float("nan"), float("inf"), -1.0, 0.0):
                with self.subTest(field=field, invalid=invalid):
                    root, record = self._build_store()
                    changed = record.to_dict()
                    changed[field] = invalid
                    self._write_record(root, changed)
                    with self.assertRaises(ValidationError):
                        LabelStore.load(root)
        for invalid in ("false", "true", 0, 1, [], {}, None):
            with self.subTest(field="is_surge", invalid=invalid):
                root, record = self._build_store()
                changed = {**record.to_dict(), "is_surge": invalid}
                self._write_record(root, changed)
                with self.assertRaises(ValidationError):
                    LabelStore.load(root)

    def test_label_record_parser_rejects_coercible_valid_numeric_values(self) -> None:
        _root, record = self._build_store()
        base = record.to_dict()
        for field in ("baseline_mean", "future_peak_mean", "realized_max_multiple"):
            with self.subTest(field=field), self.assertRaises(ValidationError):
                LabelRecord.from_dict({**base, field: str(base[field])})
        with self.assertRaises(ValidationError):
            LabelRecord.from_dict({**base, "is_surge": str(base["is_surge"]).lower()})

    def test_manifest_versions_counts_and_required_identity_types_are_strict(self) -> None:
        for field, invalids in {
            "store_version": (True, "1", 1.0, None),
            "record_count": (True, "1", 1.0, None),
            "archive_path": (False, 1, [], {}),
            "archive_sha256": (False, 1, "", "not-a-hash"),
            "calculator": (False, 1, [], {}),
            "label_contract": (False, "contract", [], None),
        }.items():
            for invalid in invalids:
                with self.subTest(field=field, invalid=invalid):
                    root, _record = self._build_store()
                    manifest = self._manifest(root)
                    manifest[field] = invalid
                    self._write_manifest(root, manifest)
                    with self.assertRaises(ValidationError):
                        LabelStore.load(root)

    def test_selected_archive_rows_reject_invalid_price_date_and_symbol_types(self) -> None:
        cases = [("adjusted_close", value) for value in
                 (True, "100.0", None, [], {}, float("nan"), float("inf"), 0, -1)]
        cases += [("as_of_date", value) for value in (True, 123, "not-a-date")]
        cases += [("symbol", value) for value in (123, False, [], {})]
        for field, invalid in cases:
            with self.subTest(field=field, invalid=invalid):
                root, _record = self._build_store()
                archive = json.loads(Path(self._manifest(root)["archive_path"]).read_text())
                archive["bars_by_symbol"]["DEMO"][0][field] = invalid
                self._rewrite_archive(root, archive)
                with self.assertRaises(ValidationError):
                    LabelStore.load(root)

    def test_rebound_archive_shape_and_insufficient_selected_history_fail_closed(self) -> None:
        for variant in ("not_an_object", "missing_bars", "bars_not_an_object", "selected_not_a_list", "short_horizon"):
            with self.subTest(variant=variant):
                root, _record = self._build_store()
                archive = json.loads(Path(self._manifest(root)["archive_path"]).read_text())
                if variant == "not_an_object":
                    archive = []
                elif variant == "missing_bars":
                    archive.pop("bars_by_symbol")
                elif variant == "bars_not_an_object":
                    archive["bars_by_symbol"] = []
                elif variant == "selected_not_a_list":
                    archive["bars_by_symbol"]["DEMO"] = {}
                else:
                    archive["bars_by_symbol"]["DEMO"] = _bars(self.AS_OF, post=10)
                self._rewrite_archive(root, archive)
                with self.assertRaises(ValidationError):
                    LabelStore.load(root)

    def test_missing_manifest_record_fields_and_malformed_json_are_typed_rejections(self) -> None:
        root, record = self._build_store()
        base_manifest = self._manifest(root)
        for field in base_manifest:
            with self.subTest(manifest_missing=field):
                missing = {key: value for key, value in base_manifest.items() if key != field}
                self._write_manifest(root, missing)
                with self.assertRaises(ValidationError):
                    LabelStore.load(root)
        self._write_manifest(root, base_manifest)
        for field in record.to_dict():
            with self.subTest(record_missing=field):
                missing = {key: value for key, value in record.to_dict().items() if key != field}
                self._write_record(root, missing)
                with self.assertRaises(ValidationError):
                    LabelStore.load(root)
        for filename in ("manifest.json", "labels.jsonl"):
            for malformed in ("{not-json", "[]"):
                with self.subTest(filename=filename, malformed=malformed):
                    self._write_manifest(root, base_manifest)
                    self._write_record(root, record.to_dict())
                    (root / filename).write_text(malformed)
                    with self.assertRaises(ValidationError):
                        LabelStore.load(root)

    def test_exclusions_are_explicit_not_defaults(self) -> None:
        records, exclusions = build_label_records(
            {"DEMO": _bars(self.AS_OF)},
            [
                ("cik_00000002", self.AS_OF.isoformat()),
                ("cik_00000001", self.AS_OF.isoformat()),
            ],
            {"cik_00000001": "DEMO"},
        )
        self.assertEqual(len(records), 1)
        self.assertEqual(len(exclusions), 1)
        self.assertEqual(exclusions[0]["reason"], "no_symbol_mapping")
        short, exclusions_b = build_label_records(
            {"DEMO": _bars(self.AS_OF, post=10)},
            [("cik_00000001", self.AS_OF.isoformat())],
            {"cik_00000001": "DEMO"},
        )
        self.assertEqual(short, [])
        self.assertEqual(
            exclusions_b[0]["reason"], "incomplete_six_month_price_horizon"
        )

    def test_case_key_parsing(self) -> None:
        self.assertEqual(
            parse_case_key("cik_0000316709:2025-05-30"),
            ("cik_0000316709", "2025-05-30"),
        )
        with self.assertRaises(ValidationError):
            parse_case_key("schw:2025-05-30")


if __name__ == "__main__":
    unittest.main()
