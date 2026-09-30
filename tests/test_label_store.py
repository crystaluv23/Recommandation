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
    parse_case_key,
    write_label_store,
)
from stock_opportunity_agent.cases.outcomes import six_month_smoothed_multiple
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
        records, exclusions = build_label_records(
            {"DEMO": bars},
            [("cik_00000001", self.AS_OF.isoformat())],
            {"cik_00000001": "DEMO"},
        )
        self.assertEqual(exclusions, [])
        self.assertEqual(len(records), 1)
        root = Path(tempfile.mkdtemp()) / "outcome-label-store-v1"
        write_label_store(
            root,
            records=records,
            archive_path="/dev/null",
            archive_sha256="0" * 64,
            created_at="2026-10-01T00:00:00+00:00",
        )
        return root, records[0]

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
        self.assertTrue(truth["is_surge"])
        self.assertEqual(truth["magnitude"], "2-3x")

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
        base = {
            "company_id": "cik_00000001",
            "as_of_date": "2025-01-15",
            "symbol": "DEMO",
            "baseline_mean": 100.0,
            "baseline_dates": [f"2025-01-{day:02d}" for day in range(9, 14)],
            "future_peak_mean": 220.0,
            "future_peak_dates": [f"2025-04-{day:02d}" for day in range(25, 30)],
            "horizon_end": "2025-07-15",
            "realized_max_multiple": 2.2,
            "is_surge": True,
            "magnitude": "2-3x",
        }
        LabelRecord.from_dict(base)
        for mutation, message in (
            ({"magnitude": "3-10x"}, "magnitude disagrees"),
            ({"is_surge": False}, "is_surge disagrees"),
            ({"realized_max_multiple": 0.0}, "finite and positive"),
        ):
            with self.subTest(mutation=mutation):
                with self.assertRaisesRegex(ValidationError, message):
                    LabelRecord.from_dict({**base, **mutation})
        missing = {key: value for key, value in base.items() if key != "symbol"}
        with self.assertRaisesRegex(ValidationError, "missing fields"):
            LabelRecord.from_dict(missing)

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
