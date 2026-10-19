"""Offline native orientation wiring; fixtures are not independent role evidence."""

from copy import deepcopy
from dataclasses import asdict
from datetime import datetime, timezone
import json
from pathlib import Path
import sys
import tempfile
from unittest import TestCase
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import run_reviewed_orientation_stage as stage

from stock_opportunity_agent.artifacts import atomic_write_json
from stock_opportunity_agent.data.raw_info import RawInfoDocument, RawInfoStore
from stock_opportunity_agent.models import ValidationError
from stock_opportunity_agent.research.evolution_core import ResearchState
from stock_opportunity_agent.research.evolution_core import RuntimeBudgetExceeded
from stock_opportunity_agent.research.local_role_exchange import LocalRoleExchange
from stock_opportunity_agent.signal_library import SignalRegistry


class ReviewedOrientationStageTests(TestCase):
    def setUp(self):
        network = patch("socket.socket", side_effect=AssertionError("network forbidden"))
        network.start()
        self.addCleanup(network.stop)

    def _read(self, path):
        return json.loads(path.read_text())

    def _files(self, root):
        return {str(path.relative_to(root)): path.read_bytes()
                for path in root.rglob("*") if path.is_file()}

    def _fixture(self, directory):
        """Use bound local originals; replace only source qualification, not core."""
        base = Path(directory).resolve()
        stores = {}
        source_inputs = {}
        for name, issuer in (("bmbl", "cik_0001830043"), ("enb", "cik_0000895728")):
            documents = []
            forms = (("10-Q", "2025-08-01", "Quarterly operations, products, services and risks."),
                     ("8-K", "2025-06-20", "Current financing announcement only.")) if name == "bmbl" else (
                         ("10-K", "2025-02-14", "Annual business operations include transmission and distribution services. Customers contract for capacity; segments face operating risks."),)
            for index, (form, date, content) in enumerate(forms):
                instant = datetime.fromisoformat(date).replace(tzinfo=timezone.utc)
                documents.append(RawInfoDocument.create(
                    document_id=f"{name}_filing_{index}", company_id=issuer,
                    source_type="filing", published_at=instant, available_at=instant,
                    content=content, metadata={"form": form},
                ))
            if name == "bmbl":
                instant = datetime(2025, 9, 29, tzinfo=timezone.utc)
                rows = [{"as_of_date": f"2025-09-{day}", "adjusted_close": close}
                        for day, close in ((22, 10), (23, 11), (24, 12),
                                           (25, 13), (26, 14), (29, 15))]
                documents.append(RawInfoDocument.create(
                    document_id="bmbl_market", company_id=issuer, source_type="market_data",
                    published_at=instant, available_at=instant, content=json.dumps(rows),
                ))
            store_root = base / name
            stores[str(store_root)] = RawInfoStore(store_root, documents=documents)
            source_inputs[name] = base / f"{name}-source-input.json"
            atomic_write_json(source_inputs[name], {"reviewed_source_snapshot": {
                "root": str(store_root), "unit_only": True,
            }})
        registry = base / "registry"
        SignalRegistry(registry).install_catalog(ROOT / "configs/signals_v1.json")
        oracle = base / "independent-oracle.json"
        atomic_write_json(oracle, {
            "fixed_denominator": {"proposer": 1, "H_init": 3},
            "proposer_case": {"sample_id": "p01"},
            "H_init_cases": [{"sample_id": value} for value in ("h01", "h02", "h03")],
            "unit_oracle_sentinel": "ORACLE_MUST_NEVER_BE_SENT_TO_ROLE",
        })
        code = base / "bound-code.py"
        code.write_text("# isolated unit code binding\n")
        for attribute, value in (("SOURCE_INPUTS", source_inputs), ("REGISTRY", registry)):
            context = patch.object(stage, attribute, value)
            context.start()
            self.addCleanup(context.stop)
        factory = patch.object(stage, "open_raw_info_store",
                               side_effect=lambda root, **kwargs: stores[str(root)])
        factory.start()
        self.addCleanup(factory.stop)
        root = base / "stage"
        with patch.object(stage, "_code_bindings", return_value=[stage.binding(code)]):
            prepared = stage.prepare(root, oracle)
        self.assertEqual(prepared["new_role_answers"], 0)
        return {"root": root, "oracle": oracle, "code": code}

    def _answer_pending(self, root, result):
        exchange = LocalRoleExchange(root / "exchange", max_calls=24)
        for pending in result["pending"]:
            if pending["sample_id"] == "p01":
                seed = self._read(root / "inputs.json")["seed_plan"]
                answer = {"B": seed["basic_info_policy"],
                    "H_init": seed["initial_research_skill"] + " Check operating risks before financing hypotheses.",
                    "H_reflect": seed["reflection_skill"], "H_analyse": seed["analysis_prompt"],
                    "used_experience_refs": []}
            else:
                answer = ResearchState(next_information_needs=(
                    "Which operating performance changes were disclosed?",
                )).to_dict()
            raw = Path(pending["outbox_path"])
            self.assertTrue(raw.is_relative_to(root))
            raw.parent.mkdir(parents=True, exist_ok=True)
            raw.write_text(json.dumps(answer))
            exchange.submit(pending["request_hash"],
                            agent_id="offline-unit-fixture-not-independent-role-evidence")

    def _complete(self, root):
        for _ in range(4):
            result = stage.resume(root)
            self.assertFalse([row for row in result["outcomes"]
                              if row["status"] not in {
                                  "accepted_requires_independent_review", "awaiting_proposer",
                              }], result)
            for row in result["outcomes"]:
                if row["status"] == "awaiting_proposer":
                    self.assertEqual(row["sample_id"], "h01")
                    self.assertIn("p01", [pending["sample_id"] for pending in result["pending"]])
            if not result["pending"]:
                return result
            self._answer_pending(root, result)
        self.fail("offline fixture did not reach the bounded initial-state boundary")

    def test_native_pending_masks_identity_isolates_oracle_and_replays_idempotently(self):
        with tempfile.TemporaryDirectory() as directory:
            root = self._fixture(directory)["root"]
            first = stage.resume(root)
            self.assertEqual({row["sample_id"] for row in first["pending"]}, {"p01", "h02", "h03"})
            for pending in first["pending"]:
                inbox = self._read(Path(pending["inbox_path"]))
                wire = json.dumps(inbox["messages"])
                for forbidden in ("ORACLE_MUST_NEVER_BE_SENT_TO_ROLE", "BMBL", "Bumble", "ENB", "Enbridge"):
                    self.assertNotIn(forbidden, wire)
                if pending["sample_id"] == "p01":
                    payload = json.loads(inbox["messages"][-1]["content"])["proposal_context"]
                    self.assertEqual(payload["fixed_prior"],
                                     self._read(root / "inputs.json")["proposer_prior"])
                    self.assertEqual(payload["fixed_prior"],
                                     stage.DEFAULT_EVOLUTION_PRIORS.propose_plan)
                    self.assertEqual(payload["meta_info"]["items"], [])
                    self.assertEqual(payload["available_source_types"], ["prices", "sec_filing"])
                else:
                    self.assertNotIn("output_patch_contract", inbox)
            before = self._files(root)
            self.assertEqual(stage.resume(root), first)
            self.assertEqual(self._files(root), before)
            self.assertFalse((root / "completion.json").exists())

    def test_real_core_preserves_bootstrap_and_original_accepted_step(self):
        from stock_opportunity_agent.research import compute_tools
        with tempfile.TemporaryDirectory() as directory:
            root = self._fixture(directory)["root"]
            captured = []
            computed_cards = []
            original = stage.LLMResearchController.initialize
            original_compute = compute_tools.compute_metric
            def capture(controller, *args, **kwargs):
                step = original(controller, *args, **kwargs)
                captured.append((deepcopy(args[0].to_dict()), step))
                return step
            def capture_compute(*args, **kwargs):
                value = original_compute(*args, **kwargs)
                computed_cards.append(deepcopy(value))
                return value
            with patch.object(stage.LLMResearchController, "initialize", new=capture), \
                 patch.object(compute_tools, "compute_metric", new=capture_compute), \
                 patch.object(stage, "_tripwire", side_effect=AssertionError("tail executed")) as tail:
                result = self._complete(root)
            tail.assert_not_called()
            self.assertEqual(result["independent_receipts"], 4)
            self.assertFalse(result["labels_read"])
            self.assertFalse(result["completed_fast_round"])
            candidate = self._read(root / "samples/p01/plan.json")["plan"]
            bootstrap = {key: self._read(root / f"samples/{key}/bootstrap.json")
                         for key in ("h01", "h02", "h03")}
            self.assertEqual(bootstrap["h01"]["plan"], candidate)
            late = bootstrap["h01"]
            self.assertEqual(late["evaluation_anchor"]["mean_adjusted_close"], 13)
            self.assertTrue(computed_cards)
            self.assertEqual(computed_cards[0]["params"], {"window_days": 180})
            self.assertEqual(computed_cards[0]["values"]["window_trading_days"], 6)
            self.assertEqual(late["computed_metrics"], [{"readable":
                compute_tools.format_computed_card_readable(computed_cards[0])}])
            for key, value in bootstrap.items():
                self.assertTrue(value["document_channel_set_by_core"])
                saved = self._read(root / f"samples/{key}/initial_state.json")
                self.assertTrue(any(plan == value["plan"] and saved["state"] == step.value.to_dict()
                                    and saved["usage"] == asdict(step.usage)
                                    and saved["metadata"] == dict(step.metadata)
                                    for plan, step in captured))
                self.assertEqual(saved["native_budget_usage"], saved["usage"])
                wire = self._read(root / "exchange/inbox" / (saved["request_hashes"][-1] + ".json"))
                payload = json.loads(wire["messages"][-1]["content"])
                self.assertEqual(payload["initial_research_skill"], value["plan"]["initial_research_skill"])
                if key != "h01":
                    self.assertIsNone(value["evaluation_anchor"])
                    self.assertEqual(value["computed_metrics"], [])
                    self.assertNotIn("evaluation_anchor", payload)
                    self.assertNotIn("computed_metrics", payload)
                else:
                    self.assertEqual(payload["evaluation_anchor"], value["evaluation_anchor"])
                    self.assertEqual(payload["computed_metrics"], value["computed_metrics"])
            early_rows = bootstrap["h03"]["bundle"]["requests"]
            operating = next(row for row in early_rows
                             if row["request"]["request_id"] == "orientation.v1.operating_report")
            self.assertEqual(operating["status"], "unresolved")
            self.assertEqual(operating["data_gap"]["reason"], "required_coverage_incomplete")

    def test_completed_restore_verifies_without_reentering_roles_or_dispatching(self):
        with tempfile.TemporaryDirectory() as directory:
            root = self._fixture(directory)["root"]
            result = self._complete(root)
            before = self._files(root)
            with patch.object(stage.LLMResearchController, "initialize", side_effect=AssertionError("role replay")), \
                 patch.object(stage.LLMInformationPlanProposer, "propose", side_effect=AssertionError("proposal replay")):
                self.assertEqual(stage.resume(root), result)
            self.assertEqual(self._files(root), before)
            self.assertEqual(len(list((root / "exchange/inbox").glob("*.json"))), 4)
            self.assertEqual(len(list((root / "exchange/receipts").glob("*.json"))), 4)

    def test_code_input_or_oracle_drift_rejects_before_new_requests(self):
        for target in ("code", "inputs", "oracle"):
            with self.subTest(target=target), tempfile.TemporaryDirectory() as directory:
                fixture = self._fixture(directory)
                root = fixture["root"]
                path = root / "inputs.json" if target == "inputs" else fixture[target]
                path.write_text(path.read_text() + "\n ") if target != "inputs" else atomic_write_json(
                    path, {**self._read(path), "unit_drift": True})
                with self.assertRaises(ValidationError):
                    stage.resume(root)
                self.assertFalse((root / "exchange/inbox").exists())

    def test_stage_hard_request_cap_rejects_before_dispatch_even_with_larger_case_cap(self):
        with tempfile.TemporaryDirectory() as directory:
            root = self._fixture(directory)["root"]
            contract = self._read(root / "contract.json")
            client = stage._client(root, contract, [])
            with self.assertRaises(RuntimeBudgetExceeded):
                client.complete_json(
                    stage="unit_orientation_hardcap", system_prompt="Offline wire fixture.",
                    payload={"text": "x" * 132000}, max_output_tokens=20,
                    max_request_tokens=256000, temperature=0, allow_outcomes=False,
                )
            self.assertFalse(list((root / "exchange/inbox").glob("*.json")))
            self.assertFalse(list((root / "exchange/receipts").glob("*.json")))
            events = []
            first = stage._client(root, contract, events, sample_id="h02")
            second = stage._client(root, contract, events, sample_id="h03")
            event = {"event_type": "structured_validation_correction",
                     "details": {"paths": ["supporting_evidence[0]"]}}
            original = deepcopy(event)
            first.on_progress(event)
            second.on_progress(event)
            self.assertEqual(events, [
                {"sample_id": "h02", "event": original},
                {"sample_id": "h03", "event": original},
            ])
            self.assertEqual(event, original)
            event["details"]["paths"].append("later caller mutation")
            self.assertEqual(events[0]["event"], original)
            self.assertEqual(events[1]["event"], original)

    def test_tampered_accepted_proposal_does_not_replace_h01_plan(self):
        with tempfile.TemporaryDirectory() as directory:
            root = self._fixture(directory)["root"]
            first = stage.resume(root)
            self._answer_pending(root, first)
            second = stage.resume(root)
            self.assertEqual([row["sample_id"] for row in second["pending"]], ["h01"])
            path = root / "samples/p01/plan.json"
            changed = self._read(path)
            accepted_plan = deepcopy(changed["plan"])
            changed["plan"]["initial_research_skill"] += " Tampered stored instruction."
            atomic_write_json(path, changed)
            with patch.object(stage, "_run_initial", wraps=stage._run_initial) as execute_initial:
                result = stage.resume(root)
            failure = next(row for row in result["outcomes"] if row["sample_id"] == "p01")
            self.assertEqual(failure["status"], "stage_failed")
            self.assertNotIn("h01", [call.args[1]["sample_id"]
                                      for call in execute_initial.call_args_list])
            blocked = next(row for row in result["outcomes"] if row["sample_id"] == "h01")
            self.assertEqual(blocked["status"], "blocked_by_proposer")
            self.assertEqual({row["sample_id"] for row in result["outcomes"]},
                             {"p01", "h01", "h02", "h03"})
            self.assertFalse((root / "completion.json").exists())
            self.assertEqual(self._read(root / "samples/h01/bootstrap.json")["plan"],
                             accepted_plan)
            self.assertEqual(len(list((root / "exchange/inbox").glob("*.json"))), 4)
