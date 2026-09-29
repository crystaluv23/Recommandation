"""Content-level tests for the closed deterministic computation registry."""

import json
import unittest
from datetime import datetime, timedelta, timezone

from stock_opportunity_agent.data.raw_info import RawInfoDocument
from stock_opportunity_agent.models import ValidationError
from stock_opportunity_agent.research.compute_tools import (
    COMPUTE_METRIC_REGISTRY,
    collect_adjusted_close_bars,
    compute_metric,
    compute_metric_requests,
)


AS_OF = datetime(2025, 7, 31, tzinfo=timezone.utc)


def market_document(rows: list[tuple[str, float]]) -> RawInfoDocument:
    available = AS_OF
    return RawInfoDocument.create(
        document_id="market-fixture",
        company_id="issuer",
        source_type="market_data",
        published_at=available,
        available_at=available,
        content=json.dumps(
            {"rows": [{"as_of_date": d, "adjusted_close": c} for d, c in rows]}
        ),
    )


BARS = [
    ("2025-01-02", 10.0),
    ("2025-02-03", 11.0),
    ("2025-03-03", 9.0),
    ("2025-04-01", 12.0),
    ("2025-05-01", 13.0),
    ("2025-06-02", 11.5),
    ("2025-07-01", 12.5),
    ("2025-07-30", 13.75),
]


class ComputeToolsTests(unittest.TestCase):
    def test_v146_price_shape_closed_form_values_and_labels(self):
        card = compute_metric(
            "price_shape",
            {"window_days": 180},
            documents=(market_document(BARS),),
            as_of=AS_OF,
        )
        self.assertEqual(card["schema_version"], "computed-metric-card-v1")
        values = card["values"]
        self.assertEqual(values["window_trading_days"], len(BARS))
        self.assertEqual(values["first_close"], 10.0)
        self.assertEqual(values["last_close"], 13.75)
        self.assertEqual(values["high"], 13.75)
        self.assertEqual(values["low"], 9.0)
        # 10.0 -> 13.75 is +37.5%: an uptrend under the fixed vocabulary.
        self.assertAlmostEqual(values["return_pct"], 37.5, places=3)
        self.assertEqual(card["labels"]["trend"], "uptrend")
        # Max drawdown: peak 11.0 -> trough 9.0 = -18.18%.
        self.assertAlmostEqual(values["max_drawdown_pct"], -18.1818, places=3)
        self.assertEqual(
            card["literal_refs"],
            [
                {"as_of_date": "2025-01-02", "adjusted_close": 10.0},
                {"as_of_date": "2025-07-30", "adjusted_close": 13.75},
            ],
        )

    def test_v146_registry_rejects_unknown_metrics_and_out_of_bounds_params(self):
        docs = (market_document(BARS),)
        with self.assertRaises(ValidationError):
            compute_metric("sharpe_ratio", {}, documents=docs, as_of=AS_OF)
        with self.assertRaises(ValidationError):
            compute_metric(
                "price_shape", {"window_days": 10}, documents=docs, as_of=AS_OF
            )
        with self.assertRaises(ValidationError):
            compute_metric(
                "price_shape", {"window_days": 30, "extra": 1},
                documents=docs, as_of=AS_OF,
            )

    def test_v146_return_between_uses_exact_literal_boundaries(self):
        card = compute_metric(
            "return_between",
            {"from_offset_days": 6, "to_offset_days": 0},
            documents=(market_document(BARS),),
            as_of=AS_OF,
        )
        # Six trading rows back from the latest = 2025-03-03 (9.0);
        # the later boundary is the latest close (13.75).
        self.assertEqual(card["values"]["from_date"], "2025-03-03")
        self.assertEqual(card["values"]["from_close"], 9.0)
        self.assertAlmostEqual(
            card["values"]["return_pct"], (13.75 / 9.0 - 1.0) * 100.0, places=3
        )
        self.assertEqual(len(card["literal_refs"]), 2)

    def test_v146_distance_to_threshold_derives_from_anchor(self):
        anchor = {
            "status": "available",
            "mean_adjusted_close": 1.57,
        }
        docs = (market_document([("2025-07-29", 1.5), ("2025-07-30", 2.18)]),)
        card = compute_metric(
            "distance_to_threshold",
            {"multiple": 2.0},
            documents=docs,
            as_of=AS_OF,
            anchor=anchor,
        )
        self.assertAlmostEqual(card["values"]["derived_threshold"], 3.14, places=6)
        self.assertEqual(card["values"]["recent_close"], 2.18)
        self.assertEqual(card["labels"]["crossing"], "below_threshold")
        # gap = 2.18/3.14 - 1 ≈ -30.57%
        self.assertAlmostEqual(card["values"]["gap_pct"], -30.5732, places=3)

    def test_v146_batch_requests_are_bounded_and_pit_checked(self):
        docs = (market_document(BARS),)
        cards = compute_metric_requests(
            [
                {"metric": "price_shape", "params": {"window_days": 90}},
                {"metric": "return_between", "params": {"from_offset_days": 3, "to_offset_days": 0}},
            ],
            documents=docs,
            as_of=AS_OF,
        )
        self.assertEqual([card["metric"] for card in cards], ["price_shape", "return_between"])
        with self.assertRaises(ValidationError):
            compute_metric_requests(
                [{"metric": "price_shape", "params": {"window_days": 90}}] * 3,
                documents=docs,
                as_of=AS_OF,
            )
        future_doc = RawInfoDocument.create(
            document_id="market-future",
            company_id="issuer",
            source_type="market_data",
            published_at=AS_OF + timedelta(days=1),
            available_at=AS_OF + timedelta(days=1),
            content="{}",
        )
        with self.assertRaises(ValidationError):
            collect_adjusted_close_bars((future_doc,), AS_OF)

    def test_v146_registry_is_closed_and_versioned(self):
        self.assertEqual(
            sorted(COMPUTE_METRIC_REGISTRY),
            ["distance_to_threshold", "price_shape", "return_between"],
        )
        for entry in COMPUTE_METRIC_REGISTRY.values():
            self.assertIn("description", entry)
            self.assertIn("params", entry)


if __name__ == "__main__":
    unittest.main()
