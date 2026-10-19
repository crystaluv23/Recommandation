"""Synthetic administrative counterexamples; no research runtime or model calls."""
from copy import deepcopy
from datetime import datetime, timedelta, timezone
import hashlib
import importlib.util
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("project_meta", ROOT / "scripts/check_project.py")
META = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(META)


class ProjectMetaTest(unittest.TestCase):
    """Exercise action, evidence, stagnation, control and archival boundaries."""

    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        self.now = datetime(2026, 10, 19, 12, tzinfo=timezone.utc)
        for name, body in {
            "consumer.md": "Synthetic local check; live consumption remains unverified.",
            "benefit.md": "Synthetic evaluation proposal; no independent result.",
            "trial-a.md": "Synthetic first trial: feedback was not consumed.",
            "trial-b.md": "Synthetic second trial: the consumer boundary failed again.",
            "review.md": "Synthetic review: the old check skipped the actual consumer.",
            "source.md": "Synthetic premise: historical source version still pending.",
            "authorization.md": "Synthetic authorization: at most one full trial.",
            "freeze.md": "Synthetic frozen revision and manifest receipt.",
        }.items():
            (self.root / name).write_text(body + "\n")
        history = b"Historical synthetic status bytes\n"
        (self.root / "history.md").write_bytes(history)
        # Independent small ledger; never transform the real project's research state.
        self.state = {
            "schema_version": 2,
            "objective": "Verify feedback consumption in a synthetic research pipeline",
            "goal_snapshot": {"status": "none", "checked_at": self.now.isoformat()},
            "acceptance": [
                {"id": "feedback", "required_level": "live", "level": "local",
                 "closed": False, "evidence": ["consumer.md"],
                 "remaining": "Actual successor consumption remains unverified"},
                {"id": "benefit", "required_level": "independent", "level": "unknown",
                 "closed": False, "evidence": ["benefit.md"],
                 "remaining": "Independent benefit has not been evaluated"},
            ],
            "iterations": [
                {"id": "trial-a", "strategy": "full_after_repair",
                 "failure_families": ["feedback_loss"], "acceptance_advances": [],
                 "evidence": ["trial-a.md"]},
                {"id": "trial-b", "strategy": "full_after_repair",
                 "failure_families": ["feedback_loss"], "acceptance_advances": [],
                 "evidence": ["trial-b.md"]},
            ],
            "review": {
                "after_iteration": "trial-b", "evidence": ["review.md"],
                "blind_spots": ["The prior check skipped actual consumer composition"],
                "decision": {
                    "acceptance_id": "feedback", "kind": "diagnose",
                    "strategy": "inspect_actual_consumer",
                    "action": "Trace a persisted feedback record into the consumer payload",
                    "question": "Does the consumer receive the persisted feedback record?",
                    "pass": "The record is absent from the actual consumer payload",
                    "fail": "The record is present in the actual consumer payload",
                    "on_pass": "Repair the producer-to-consumer projection",
                    "on_fail": "Stop this diagnosis and inspect interpretation instead",
                    "stop": "Stop after locating the first missing boundary",
                },
            },
            "successor_prerequisites": [
                {"id": "source_version", "status": "pending", "evidence": ["source.md"]},
            ],
            "successor_plan": None,
            "history_archive": {"path": "history.md", "bytes": len(history),
                                "sha256": hashlib.sha256(history).hexdigest()},
        }

    def check(self, **kwargs):
        return META.check_state(self.root, self.state, now=self.now, **kwargs)

    def ready(self):
        """Prepare administrative prerequisites without advancing research evidence."""
        self.state["goal_snapshot"]["status"] = "active"
        self.state["successor_prerequisites"][0]["status"] = "met"
        decision = self.state["review"]["decision"]
        decision["kind"] = "full_successor"
        self.state["successor_plan"] = {
            "strategy": decision["strategy"], "acceptance_id": "feedback",
            "why_full_run": "The synthetic target needs cross-cycle persisted consumption",
            "budget": "At most one full trial as recorded in authorization.md",
            "authorization_evidence": ["authorization.md"], "freeze_evidence": ["freeze.md"],
            "revision": "a" * 40, "manifest_sha256": "b" * 64,
        }

    def run_cli(self, *, before_successor=False, raw=None):
        """Run the actual script's loading and exit boundary in an isolated workspace."""
        for name in META.REQUIRED:
            target = self.root / name
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text("Synthetic administrative entry.\n")
        script = self.root / "scripts/check_project.py"
        script.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(ROOT / "scripts/check_project.py", script)
        self.state["goal_snapshot"]["checked_at"] = datetime.now(timezone.utc).isoformat()
        ledger = self.root / "progress/convergence.json"
        ledger.write_text(json.dumps(self.state) if raw is None else raw)
        command = [sys.executable, str(script)]
        if before_successor:
            command.append("--before-successor")
        return subprocess.run(command, cwd=self.root, capture_output=True, text=True,
                              check=False, timeout=10)

    def test_diagnosis_can_be_consistent_while_successor_is_blocked(self):
        self.assertEqual(self.check(), [])
        failures = self.check(before_successor=True)
        self.assertTrue(any("pending" in item for item in failures))
        self.assertIn("successor blocked: goal is not active", failures)

    def test_two_stagnant_rounds_require_current_review_without_shared_failures(self):
        for item in self.state["iterations"]:
            item["failure_families"] = []
        self.state["review"]["after_iteration"] = "trial-a"
        self.assertTrue(any("current review" in item for item in self.check()))

    def test_renaming_strategies_and_clearing_families_cannot_hide_stagnation(self):
        for index, item in enumerate(self.state["iterations"]):
            item.update(strategy=f"renamed-{index}", failure_families=[])
        self.state["review"] = None
        self.assertTrue(any("current review" in item for item in self.check()))

    def test_recurrence_requires_review_even_with_a_valid_latest_advance(self):
        self.state["iterations"][-1]["strategy"] = "different"
        self.state["iterations"][-1]["acceptance_advances"] = [
            {"acceptance_id": "feedback", "level": "live", "evidence": ["consumer.md"]}
        ]
        self.state["acceptance"][0]["level"] = "live"
        self.state["review"] = None
        self.assertTrue(any("current review" in item for item in self.check()))

    def test_unchanged_strategy_needs_new_evidence_and_distinguishing_variable(self):
        decision = self.state["review"]["decision"]
        decision["strategy"] = self.state["iterations"][-1]["strategy"]
        self.assertTrue(any("distinguishing_variable" in item for item in self.check()))
        decision.update(new_evidence="Actual producer shape differs from the old fixture",
                        distinguishing_variable="Producer-to-consumer serialized shape")
        self.assertEqual(self.check(), [])

    def test_non_successor_actions_cannot_be_relabelled_by_matching_plan_strategy(self):
        self.ready()
        for kind in ("diagnose", "repair", "stop", "human_decision"):
            with self.subTest(kind=kind):
                self.state["review"]["decision"]["kind"] = kind
                self.assertIn("successor blocked: reviewed decision is not full_successor",
                              self.check(before_successor=True))

    def test_unknown_decision_kind_is_rejected(self):
        self.state["review"]["decision"]["kind"] = "continue_somehow"
        self.assertIn("unknown review decision kind", self.check())

    def test_stop_and_human_decision_need_no_fabricated_experiment_or_new_evidence(self):
        decision = self.state["review"]["decision"]
        decision["strategy"] = self.state["iterations"][-1]["strategy"]
        for key in ("question", "pass", "fail", "on_pass", "on_fail"):
            del decision[key]
        for kind in ("stop", "human_decision"):
            with self.subTest(kind=kind):
                decision["kind"] = kind
                self.assertEqual(self.check(), [])

    def test_experimental_actions_require_observations_and_both_next_actions(self):
        decision = self.state["review"]["decision"]
        for kind in ("diagnose", "repair", "full_successor"):
            decision["kind"] = kind
            for field in ("question", "pass", "fail", "on_pass", "on_fail"):
                with self.subTest(kind=kind, field=field):
                    value = decision.pop(field)
                    self.assertIn(f"review: missing {field}", self.check())
                    decision[field] = value

    def test_both_observations_may_legitimately_stop_the_same_action(self):
        decision = self.state["review"]["decision"]
        decision["on_pass"] = decision["on_fail"] = "Stop this bounded diagnostic"
        self.assertEqual(self.check(), [])

    def test_review_target_must_exist_and_non_stop_target_must_be_open(self):
        decision = self.state["review"]["decision"]
        decision["acceptance_id"] = "missing"
        self.assertIn("review references unknown acceptance item", self.check())
        decision["acceptance_id"] = "feedback"
        self.state["acceptance"][0].update(level="live", closed=True)
        self.assertIn("review must target an open acceptance item", self.check())
        decision["kind"] = "stop"
        self.assertEqual(self.check(), [])
        decision["acceptance_id"] = "missing"
        self.assertIn("review references unknown acceptance item", self.check())

    def test_successor_cannot_target_a_different_or_unknown_acceptance_item(self):
        self.ready()
        for target in ("benefit", "missing"):
            with self.subTest(target=target):
                self.state["successor_plan"]["acceptance_id"] = target
                self.assertIn("successor acceptance differs from reviewed decision",
                              self.check(before_successor=True))

    def test_matching_plan_and_review_cannot_target_closed_acceptance(self):
        self.ready()
        self.state["acceptance"][0].update(level="live", closed=True)
        self.assertIn("review must target an open acceptance item",
                      self.check(before_successor=True))

    def test_local_pass_cannot_close_live_or_independent_goal(self):
        for item in self.state["acceptance"]:
            with self.subTest(item=item["id"]):
                item.update(closed=True, level="local")
                self.assertTrue(any("closure below" in failure for failure in self.check()))
                item["closed"] = False

    def test_local_pass_cannot_disguise_a_goal_advance(self):
        self.state["iterations"][-1]["acceptance_advances"] = [
            {"acceptance_id": "feedback", "level": "local", "evidence": ["consumer.md"]}
        ]
        self.assertIn("advance substitutes lower-level evidence", self.check())

    def test_latest_advance_cannot_exceed_current_acceptance_evidence_level(self):
        self.state["iterations"][-1]["acceptance_advances"] = [
            {"acceptance_id": "feedback", "level": "live", "evidence": ["consumer.md"]}
        ]
        self.assertIn("latest advance exceeds current acceptance evidence level", self.check())
        self.state["acceptance"][0]["level"] = "live"
        self.assertEqual(self.check(), [])

    def test_unknown_cannot_be_a_required_acceptance_level(self):
        self.state["acceptance"][0]["required_level"] = "unknown"
        self.assertIn("invalid acceptance level", self.check())

    def test_closed_claim_requires_accessible_evidence(self):
        self.state["acceptance"][0].update(closed=True, level="live", evidence=["missing.md"])
        self.assertTrue(any("inaccessible evidence" in failure for failure in self.check()))

    def test_valid_administrative_fixture_does_not_close_or_mutate_research_goals(self):
        self.ready()
        before = deepcopy(self.state)
        self.assertEqual(self.check(before_successor=True), [])
        self.assertEqual(self.state, before)
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
            self.assertIn("successor blocked: goal receipt stale or future",
                          self.check(before_successor=True))

    def test_pending_premise_blocks_otherwise_ready_successor(self):
        self.ready()
        self.state["successor_prerequisites"][0]["status"] = "pending"
        self.assertTrue(any("pending" in failure for failure in self.check(before_successor=True)))

    def test_evidence_cannot_escape_repository(self):
        self.state["review"]["evidence"] = ["../outside.md", str(self.root / "review.md")]
        self.assertEqual(sum("inaccessible evidence" in item for item in self.check()), 2)

    def test_missing_freeze_or_plan_drift_is_rejected(self):
        self.ready()
        self.state["successor_plan"].update(revision="main", manifest_sha256="latest",
                                            strategy="old_strategy")
        failures = self.check(before_successor=True)
        self.assertIn("successor requires exact frozen revision", failures)
        self.assertIn("successor requires exact manifest hash", failures)
        self.assertIn("successor strategy differs from reviewed decision", failures)

    def test_full_successor_requires_rationale_budget_authorization_and_freeze(self):
        self.ready()
        plan = self.state["successor_plan"]
        for field in ("why_full_run", "budget", "authorization_evidence", "freeze_evidence"):
            with self.subTest(field=field):
                value = plan.pop(field)
                self.assertTrue(self.check(before_successor=True))
                plan[field] = value

    def test_historical_status_is_byte_preserved(self):
        (self.root / "history.md").write_bytes(b"Silently revised history\n")
        self.assertIn("historical status bytes/hash changed", self.check())

    def test_old_schema_is_rejected(self):
        self.state["schema_version"] = 1
        self.assertIn("unsupported meta schema", self.check())

    def test_cli_default_accepts_diagnosis_but_full_successor_rejects_it(self):
        result = self.run_cli()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.ready()
        self.state["review"]["decision"]["kind"] = "diagnose"
        result = self.run_cli(before_successor=True)
        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
        self.assertIn("reviewed decision is not full_successor", result.stdout)

    def test_cli_ready_successor_pass_is_administrative_and_leaves_research_open(self):
        self.ready()
        result = self.run_cli(before_successor=True)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("administrative only; not live/learning/benefit acceptance", result.stdout)
        saved = json.loads((self.root / "progress/convergence.json").read_text())
        self.assertEqual(saved, self.state)
        self.assertFalse(any(item["closed"] for item in saved["acceptance"]))

    def test_cli_rejects_malformed_json_and_record_shapes(self):
        for raw in ("{bad json", json.dumps({"schema_version": 2, "acceptance": [None]}), "[]"):
            with self.subTest(raw=raw):
                result = self.run_cli(before_successor=True, raw=raw)
                self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
                self.assertIn("invalid meta record", result.stdout)
                self.assertNotIn("Traceback", result.stderr)


class ProjectMetaRepositoryTest(unittest.TestCase):
    """Check the real repository separately from synthetic boundary fixtures."""

    def test_repository_current_meta_is_consistent(self):
        self.assertEqual(META.check_project(ROOT), [])


if __name__ == "__main__":
    unittest.main()
