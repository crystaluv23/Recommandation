"""Administrative counterexamples: no research runtime or model calls."""
from datetime import datetime, timedelta, timezone
import hashlib
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("project_meta", ROOT / "scripts/check_project.py")
META = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(META)


class ProjectMetaTest(unittest.TestCase):
    """Exercise evidence-level, stagnation, control and archival guard boundaries."""

    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        self.now = datetime(2026, 10, 7, 12, tzinfo=timezone.utc)
        self.state = json.loads((ROOT / "progress/convergence.json").read_text())
        (self.root / "proof.md").write_text("Test fixture evidence, not a research result.\n")
        body = b"Historical status bytes\n"
        (self.root / "history.md").write_bytes(body)
        self.state["history_archive"] = {"path": "history.md", "bytes": len(body),
                                        "sha256": hashlib.sha256(body).hexdigest()}

        def substitute(value):
            if isinstance(value, dict):
                for key, child in value.items():
                    if key == "evidence":
                        value[key] = ["proof.md"]
                    else:
                        substitute(child)
            elif isinstance(value, list):
                for child in value:
                    substitute(child)
        substitute(self.state)
        self.state["goal_snapshot"]["checked_at"] = self.now.isoformat()

    def check(self, **kwargs):
        return META.check_state(self.root, self.state, now=self.now, **kwargs)

    def ready(self):
        self.state["goal_snapshot"]["status"] = "active"
        for item in self.state["successor_prerequisites"]:
            item["status"] = "met"
        decision = self.state["review"]["decision"]
        self.state["successor_plan"] = {
            **{key: decision[key] for key in ("question", "pass", "fail", "stop", "strategy")},
            "authorization_evidence": ["proof.md"], "freeze_evidence": ["proof.md"],
            "revision": "a" * 40, "manifest_sha256": "b" * 64,
        }

    def test_diagnosis_can_be_consistent_while_successor_is_blocked(self):
        self.assertEqual(self.check(), [])
        failures = self.check(before_successor=True)
        self.assertTrue(any("pending" in item for item in failures))
        self.assertIn("successor blocked: goal is not active", failures)

    def test_two_stagnant_rounds_require_current_review_without_shared_failures(self):
        for item in self.state["iterations"]:
            item["failure_families"] = []
        self.state["review"]["after_iteration"] = "v181"
        self.assertTrue(any("current review" in item for item in self.check()))

    def test_recurrence_requires_review_even_when_strategy_changes(self):
        self.state["iterations"][-1]["strategy"] = "different"
        self.state["review"] = None
        self.assertTrue(any("current review" in item for item in self.check()))

    def test_unchanged_strategy_needs_new_evidence_and_distinguishing_variable(self):
        decision = self.state["review"]["decision"]
        decision["strategy"] = self.state["iterations"][-1]["strategy"]
        self.assertTrue(any("distinguishing_variable" in item for item in self.check()))
        decision.update(new_evidence="A real new frontier", distinguishing_variable="producer shape")
        self.assertEqual(self.check(), [])

    def test_local_pass_cannot_close_live_or_independent_goal(self):
        for item in self.state["acceptance"]:
            with self.subTest(item=item["id"]):
                item["closed"] = True
                item["level"] = "local"
                self.assertTrue(any("closure below" in failure for failure in self.check()))
                item["closed"] = False

    def test_local_pass_cannot_disguise_a_goal_advance(self):
        self.state["iterations"][-1]["acceptance_advances"] = [
            {"acceptance_id": "content_chain", "level": "local", "evidence": ["proof.md"]}
        ]
        self.assertIn("advance substitutes lower-level evidence", self.check())

    def test_unknown_cannot_be_a_required_acceptance_level(self):
        self.state["acceptance"][0]["required_level"] = "unknown"
        self.assertIn("invalid acceptance level", self.check())

    def test_closed_claim_requires_accessible_evidence(self):
        item = self.state["acceptance"][0]
        item.update(closed=True, level="live", evidence=["missing.md"])
        self.assertTrue(any("inaccessible evidence" in failure for failure in self.check()))

    def test_valid_administrative_fixture_can_pass_without_closing_research_goals(self):
        self.ready()
        self.assertEqual(self.check(before_successor=True), [])
        self.assertFalse(any(item["closed"] for item in self.state["acceptance"]))

    def test_control_limits_and_absent_goal_never_allow_successor(self):
        self.ready()
        for status in ("usageLimited", "budgetLimited", "none", "paused", "blocked", "complete"):
            with self.subTest(status=status):
                self.state["goal_snapshot"]["status"] = status
                self.assertIn("successor blocked: goal is not active", self.check(before_successor=True))

    def test_stale_or_future_receipt_cannot_authorize_successor(self):
        self.ready()
        for delta in (timedelta(minutes=-11), timedelta(minutes=1)):
            self.state["goal_snapshot"]["checked_at"] = (self.now + delta).isoformat()
            self.assertIn("successor blocked: goal receipt stale or future", self.check(before_successor=True))

    def test_pending_premise_blocks_otherwise_ready_successor(self):
        self.ready()
        self.state["successor_prerequisites"][0]["status"] = "pending"
        self.assertTrue(any("pending" in failure for failure in self.check(before_successor=True)))

    def test_evidence_cannot_escape_repository(self):
        self.state["review"]["evidence"] = ["../outside.md", str(self.root / "proof.md")]
        self.assertEqual(sum("inaccessible evidence" in item for item in self.check()), 2)

    def test_missing_freeze_or_plan_drift_is_rejected(self):
        self.ready()
        self.state["successor_plan"].update(revision="main", strategy="old_strategy")
        failures = self.check(before_successor=True)
        self.assertIn("successor requires exact frozen revision", failures)
        self.assertIn("successor strategy differs from reviewed decision", failures)

    def test_historical_status_is_byte_preserved(self):
        (self.root / "history.md").write_bytes(b"Silently revised history\n")
        self.assertIn("historical status bytes/hash changed", self.check())

    def test_malformed_record_fails_closed_at_cli_boundary(self):
        for path in META.REQUIRED:
            target = self.root / path
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text("Meta fixture\n")
        for value in ("{bad json", json.dumps({"schema_version": 1, "acceptance": [None]})):
            (self.root / "progress/convergence.json").write_text(value)
            self.assertTrue(any("invalid meta record" in failure
                                for failure in META.check_project(self.root, before_successor=True)))

    def test_repository_current_meta_is_consistent(self):
        self.assertEqual(META.check_project(ROOT), [])


if __name__ == "__main__":
    unittest.main()
