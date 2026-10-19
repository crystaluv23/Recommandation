"""Native Posthoc wiring with temporary synthetic labels and offline role fixtures."""
from copy import deepcopy
from dataclasses import asdict
from datetime import date
import json
from pathlib import Path
import subprocess
import sys
import tempfile
from unittest import TestCase
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import run_reviewed_posthoc_stage as stage
from run_reviewed_fast_prefix import _immutable_artifacts
from stock_opportunity_agent.artifacts import atomic_write_json, canonical_json_hash
from stock_opportunity_agent.cases.label_store import (
    LabelStore, build_label_records, file_sha256, write_label_store,
)
from stock_opportunity_agent.models import ValidationError
from stock_opportunity_agent.research.evolution_core import BlindPrediction, ResearchState
from stock_opportunity_agent.research.local_role_exchange import LocalRoleExchange, LocalRoleRequestPending
from tests.test_label_store import _bars


class ReviewedPosthocStageTests(TestCase):
    def setUp(self):
        self.network = patch("socket.socket", side_effect=AssertionError("network forbidden"))
        self.network.start()
        self.addCleanup(self.network.stop)

    def _read(self, path):
        return json.loads(path.read_text())

    def _files(self, root):
        return {str(path.relative_to(root)): path.read_bytes()
                for path in root.rglob("*") if path.is_file()}

    def _fixture(self, directory, *, label_company="cik_00000001"):
        """Build a hash-bound unit parent and a real small canonical label store."""
        base = Path(directory).resolve()
        repository = base / "unit-repo"
        code = repository / "src/unit.py"
        code.parent.mkdir(parents=True)
        code.write_text("# historical offline parent source\n")
        for args in (("init", "-q"), ("add", "src/unit.py"),
                     ("-c", "user.name=Offline Unit", "-c", "user.email=offline@example.invalid",
                      "-c", "commit.gpgsign=false", "commit", "-qm", "unit fixture")):
            subprocess.run(["git", "-C", str(repository), *args], check=True, capture_output=True)
        commit = subprocess.run(["git", "-C", str(repository), "rev-parse", "HEAD"],
                                check=True, capture_output=True, text=True).stdout.strip()
        as_of = date(2025, 1, 15)
        bars = _bars(as_of)
        archive = base / "unit-price-archive.json"
        atomic_write_json(archive, {"schema_version": "scheme-evolution-adjusted-prices-v1",
            "source": "offline-unit-fixture", "start_date": bars[0]["as_of_date"],
            "end_date": bars[-1]["as_of_date"], "requested_symbol_count": 1,
            "priced_symbol_count": 1, "failed_symbols": {}, "bars_by_symbol": {"DEMO": bars}})
        records, exclusions = build_label_records({"DEMO": bars}, [(label_company, as_of.isoformat())],
                                                  {label_company: "DEMO"})
        self.assertEqual(exclusions, [])
        labels = base / "unit-label-store"
        write_label_store(labels, records=records, archive_path=archive,
                          archive_sha256=file_sha256(archive), created_at="2026-10-20T00:00:00+00:00")
        label = LabelStore.load(labels).record(label_company, as_of)
        identity = {"ticker": "DEMO", "company_name": "Demo Unit Issuer",
                    "identity_aliases": ["Demo Unit Issuer", "DEMO"]}
        sample = {"sample_id": "s01", "company_id": "cik_00000001",
                  "prediction_time": as_of.isoformat() + "T00:00:00+00:00", "identity": identity}
        context = {"prediction_time": sample["prediction_time"], "basic_info": {"requests": []},
            "signal_rounds": [], "final_research_state": ResearchState(decision="finalize",
                next_information_needs=("What remains unknown for Demo Unit Issuer?",)).to_dict(),
            "runtime_termination": {"phase": "prediction_ready", "stop_reason": "finalized", "termination_trigger": None},
            "prediction_baseline": {"status": "available", "mean_adjusted_close": label.baseline_mean,
                                    "trading_dates": list(label.baseline_dates)}}
        prediction = BlindPrediction(False, "insufficient_information", None, "low",
            ("Offline prediction fixture for Demo Unit Issuer.",), ("Unit fixture only.",), "unit-session")
        parent = base / "unit-parent"
        original = base / "unit-parent-original.txt"
        original.write_text("frozen parent source fixture\n")
        payloads = {"inputs": {"sample": sample}, "expectations": {"unit_only": "PARENT_ORACLE_SENTINEL"},
                    "preflight": {"unit_fixture": True}}
        contract = {"max_local_calls": 32, "input_hash": canonical_json_hash(payloads["inputs"]),
                    "expectations_hash": canonical_json_hash(payloads["expectations"]),
                    "preflight_hash": canonical_json_hash(payloads["preflight"])}
        for name, value in {**payloads, "contract": contract}.items():
            atomic_write_json(parent / (name + ".json"), value)
        saved = {"company_id": sample["company_id"], "prediction_time": sample["prediction_time"],
                 "final_context": context, "prediction": prediction.to_dict()}
        atomic_write_json(parent / "prediction.json", saved)
        manifest = {"contract_hash": canonical_json_hash(contract), "code_files": [stage.binding(code)],
                    "originals": [stage.binding(original)], "registry_files": []}
        manifest["manifest_hash"] = canonical_json_hash(manifest)
        atomic_write_json(parent / "manifest.json", manifest)
        LocalRoleExchange(parent / "exchange", max_calls=32)
        completion = {"manifest_hash": manifest["manifest_hash"],
                      "result": {"unit_fixture": True, "completed_fast_round": False, "completed_trajectory": False},
                      "immutable_artifacts": _immutable_artifacts(parent)}
        completion["completion_hash"] = canonical_json_hash(completion)
        atomic_write_json(parent / "completion.json", completion)
        oracle = base / "unit-posthoc-oracle.json"
        atomic_write_json(oracle, {"fixed_denominator": 1, "sample_id": "s01",
            "unit_only_sentinel": "POSTHOC_ORACLE_SENTINEL", "parent": {"root": str(parent),
                "manifest_hash": manifest["manifest_hash"], "prediction_sha256": file_sha256(parent / "prediction.json"),
                "sample_key": [sample["company_id"], as_of.isoformat()]}})
        stage_code = base / "unit-stage-code.py"
        stage_code.write_text("# frozen unit stage code\n")
        for attribute, value in (("REPO", repository), ("LABEL_ROOT", labels)):
            fixture_patch = patch.object(stage, attribute, value)
            fixture_patch.start()
            self.addCleanup(fixture_patch.stop)
        return {"root": base / "posthoc", "parent": parent, "oracle": oracle, "commit": commit,
                "archive": archive, "labels": labels, "stage_code": stage_code,
                "original": original, "saved": saved, "label": label}

    def _prepare(self, fixture):
        with patch.object(stage, "_code_bindings", return_value=[stage.binding(fixture["stage_code"])]):
            result = stage.prepare(fixture["root"], fixture["oracle"], parent_root=fixture["parent"],
                                   parent_commit=fixture["commit"])
        self.assertEqual(result["role_answers"], 0)
        return fixture["root"]

    def _answer(self, root, pending, value):
        raw = Path(pending["outbox_path"])
        self.assertTrue(raw.is_relative_to(root))
        raw.parent.mkdir(parents=True, exist_ok=True)
        raw.write_text(json.dumps(value))
        LocalRoleExchange(root / "exchange", max_calls=8).submit(pending["request_hash"],
            agent_id="offline-unit-fixture-not-independent-model-evidence")

    def _complete(self, fixture, *, correction=False, fallback=False):
        root = self._prepare(fixture)
        first = stage.resume(root)
        self.assertEqual(first["status"], "pending_independent_role")
        pending = first["pending"][0]
        wire = self._read(Path(pending["inbox_path"]))
        payload = json.loads(wire["messages"][-1]["content"])
        reason = "Offline unit fixture: no research finding is asserted."
        answer = {"reflection_items": [], "selected_reflection_refs": [], "no_findings_reason": "" if correction else reason}
        self._answer(root, pending, answer)
        trace = [pending["request_hash"]]
        if correction:
            next_result = stage.resume(root)
            self.assertEqual(next_result["status"], "pending_independent_role")
            pending = next_result["pending"][0]
            self.assertEqual(pending["stage"], "blind_predictor_posthoc_reflect_correction")
            correction_payload = json.loads(self._read(Path(pending["inbox_path"]))["messages"][-1]["content"])
            self._answer(root, pending, {"base_hash": correction_payload["output_patch_contract"]["base_hash"],
                "operations": [{"op": "replace", "path": "no_findings_reason", "value": " " if fallback else reason}]})
            trace.append(pending["request_hash"])
        captured = []
        native_reflect = stage.LLMBlindPredictor.reflect

        def capture(predictor, *args, **kwargs):
            step = native_reflect(predictor, *args, **kwargs)
            captured.append(step)
            return step

        with patch.object(stage.LLMBlindPredictor, "reflect", new=capture):
            result = stage.resume(root)
        self.assertEqual(result["status"], "feedback_persisted_requires_independent_review")
        self.assertEqual(result["physical_receipts"], len(trace))
        self.assertEqual(len(captured), 1)
        feedback = self._read(root / "feedback.json")
        self.assertEqual(feedback["value"], captured[0].value.to_dict())
        self.assertEqual(feedback["metadata"], dict(captured[0].metadata))
        self.assertEqual(feedback["usage"], asdict(captured[0].usage))
        self.assertEqual(feedback["request_hashes"], trace)
        self.assertEqual(feedback["native_validation_fallback"], fallback)
        self.assertEqual(feedback["value"]["prediction_outcome"]["correct"], payload["framework_prediction_correct"])
        self.assertEqual(feedback["value"]["source_snapshot"], {
            "source_identity": feedback["value"]["source_identity"],
            "candidate_judgment_feedback": payload["candidate_judgment_feedback"],
            "magnitude_feedback": payload["magnitude_feedback"]})
        return root, result, trace

    def test_real_anonymous_posthoc_pending_uses_canonical_truth_and_is_idempotent(self):
        with tempfile.TemporaryDirectory() as directory:
            fixture = self._fixture(directory)
            root = self._prepare(fixture)
            before_parent = self._files(fixture["parent"])
            first = stage.resume(root)
            self.assertEqual(first["status"], "pending_independent_role")
            self.assertEqual(first["physical_receipts"], 0)
            pending = first["pending"][0]
            self.assertEqual(pending["stage"], "blind_predictor_posthoc_reflect")
            inbox = self._read(Path(pending["inbox_path"]))
            text = json.dumps(inbox)
            for forbidden in ("DEMO", "Demo Unit Issuer", "cik_00000001", "POSTHOC_ORACLE_SENTINEL", "PARENT_ORACLE_SENTINEL"):
                self.assertNotIn(forbidden, text)
            payload = json.loads(inbox["messages"][-1]["content"])
            truth = LabelStore.load(fixture["labels"]).ground_truth("cik_00000001", "2025-01-15")
            self.assertEqual(payload["revealed_ground_truth"], truth)
            self.assertTrue(payload["source_catalog"])
            self.assertTrue(all(row["source_kind"] == "canonical_case_facts" for row in payload["source_catalog"]))
            self.assertEqual(payload["compact_context"]["runtime_termination"],
                             fixture["saved"]["final_context"]["runtime_termination"])
            self.assertEqual(self._read(root / "contract.json")["max_local_calls"], 8)
            before = self._files(root)
            self.assertEqual(stage.resume(root), first)
            self.assertEqual(before, self._files(root))
            self.assertEqual(before_parent, self._files(fixture["parent"]))
            self.assertFalse((root / "feedback.json").exists())

    def test_accepted_feedback_and_completed_restore_preserve_exact_native_snapshot(self):
        with tempfile.TemporaryDirectory() as directory:
            fixture = self._fixture(directory)
            parent_before = self._files(fixture["parent"])
            labels_before = self._files(fixture["labels"])
            archive_before = fixture["archive"].read_bytes()
            root, result, trace = self._complete(fixture, correction=True)
            self.assertEqual(result["reflection_items"], 0)
            self.assertFalse(result["completed_trajectory"])
            self.assertFalse(result["completed_fast_round"])
            self.assertFalse(result["slow_source_published"])
            before = self._files(root)
            receives = []
            original = LocalRoleExchange.receive

            def receive(exchange, request, **kwargs):
                self.assertFalse(kwargs["allow_dispatch"])
                receives.append(canonical_json_hash(request))
                return original(exchange, request, **kwargs)

            with patch.object(stage.LLMBlindPredictor, "reflect", side_effect=AssertionError("completed role re-execution")), patch.object(
                    LocalRoleExchange, "receive", new=receive):
                restored = stage.resume(root)
            self.assertEqual(restored, {**result, "restored_without_execution": True, "immutable_artifacts_unchanged": True})
            self.assertEqual(set(receives), set(trace))
            self.assertEqual(before, self._files(root))
            self.assertEqual(parent_before, self._files(fixture["parent"]))
            self.assertEqual(labels_before, self._files(fixture["labels"]))
            self.assertEqual(archive_before, fixture["archive"].read_bytes())

    def test_completed_feedback_receipt_raw_and_inventory_tampering_reject_before_dispatch(self):
        with tempfile.TemporaryDirectory() as directory:
            fixture = self._fixture(directory)
            root, _result, trace = self._complete(fixture)
            for relative in ("feedback.json", f"exchange/receipts/{trace[0]}.json", f"exchange/outbox/{trace[0]}.txt",
                             f"cache/responses/{trace[0]}.json", f"requests/{trace[0]}.json", "unbound-extra.json"):
                with self.subTest(relative=relative):
                    path = root / relative
                    original_bytes = path.read_bytes() if path.exists() else None
                    path.write_text("{}")
                    before = self._files(root)
                    try:
                        with patch.object(LocalRoleExchange, "receive") as receive, self.assertRaises(ValidationError):
                            stage.resume(root)
                        receive.assert_not_called()
                        self.assertEqual(before, self._files(root))
                    finally:
                        path.unlink() if original_bytes is None else path.write_bytes(original_bytes)

    def test_rebound_completed_inventory_still_validates_native_receipt_and_cache(self):
        with tempfile.TemporaryDirectory() as directory:
            fixture = self._fixture(directory)
            root, _result, trace = self._complete(fixture)
            completion_path = root / "completion.json"
            original_completion = completion_path.read_bytes()
            for relative in (f"exchange/receipts/{trace[0]}.json", f"exchange/outbox/{trace[0]}.txt", f"cache/responses/{trace[0]}.json"):
                with self.subTest(relative=relative):
                    path = root / relative
                    original_bytes = path.read_bytes()
                    path.write_text("{}")
                    completion = self._read(completion_path)
                    completion.pop("completion_hash")
                    completion["immutable_artifacts"] = stage._files(root, runtime=True)
                    completion["completion_hash"] = canonical_json_hash(completion)
                    atomic_write_json(completion_path, completion)
                    before = self._files(root)
                    try:
                        with self.assertRaises(ValidationError):
                            stage._completed_restore(root, completion["manifest_hash"], self._read(root / "contract.json"))
                        self.assertEqual(before, self._files(root))
                    finally:
                        path.write_bytes(original_bytes)
                        completion_path.write_bytes(original_completion)

    def test_frozen_parent_label_archive_oracle_and_code_drift_reject_before_role(self):
        with tempfile.TemporaryDirectory() as directory:
            fixture = self._fixture(directory)
            root = self._prepare(fixture)
            paths = (fixture["parent"] / "prediction.json", fixture["parent"] / "new-parent-file.json",
                     fixture["original"], fixture["archive"], fixture["labels"] / "labels.jsonl",
                     fixture["labels"] / "manifest.json", fixture["oracle"], root / "expectations.json",
                     root / "inputs.json", fixture["stage_code"])
            for path in paths:
                with self.subTest(path=path.name):
                    original_bytes = path.read_bytes() if path.exists() else None
                    path.write_text("{}")
                    try:
                        with patch.object(stage, "StructuredRoleClient") as client, self.assertRaises(ValidationError):
                            stage.resume(root)
                        client.assert_not_called()
                        self.assertFalse((root / "exchange").exists())
                    finally:
                        path.unlink() if original_bytes is None else path.write_bytes(original_bytes)

    def test_shared_eight_call_ceiling_counts_existing_native_requests_on_resume(self):
        with tempfile.TemporaryDirectory() as directory:
            fixture = self._fixture(directory)
            root = self._prepare(fixture)
            contract = self._read(root / "contract.json")
            client = stage.StructuredRoleClient(registration=stage.get_model("independent-subagent"),
                contract=stage.StageContract(contract), workspace=root,
                local_role_exchange=LocalRoleExchange(root / "exchange", max_calls=8),
                ledger=stage.ExternalAttemptLedger(root / "unused_external_attempts.json", max_attempts=1, max_total_cost=0.01),
                allow_external=False, environ={})
            for index in range(8):
                with self.assertRaises(LocalRoleRequestPending):
                    client.complete_json(stage="unit_budget_fixture", system_prompt="Offline aggregate budget fixture.",
                        payload={"unit_fixture_index": index}, allow_outcomes=True, max_output_tokens=20)
            result = stage.resume(root)
            self.assertEqual(result["status"], "control_budget_stopped")
            self.assertEqual(result["physical_receipts"], 0)
            self.assertEqual(len(list((root / "exchange/inbox").glob("*.json"))), 8)
            before = self._files(root)
            self.assertEqual(stage.resume(root), result)
            self.assertEqual(before, self._files(root))
            self.assertFalse((root / "completion.json").exists())

    def test_unknown_canonical_key_rejects_before_prepare_dispatch(self):
        with tempfile.TemporaryDirectory() as directory:
            fixture = self._fixture(directory, label_company="cik_00000002")
            with self.assertRaises(ValidationError):
                self._prepare(fixture)
            self.assertFalse(fixture["root"].exists())

    def test_native_validation_fallback_remains_explicit_with_original_feedback(self):
        with tempfile.TemporaryDirectory() as directory:
            fixture = self._fixture(directory)
            root, result, trace = self._complete(fixture, correction=True, fallback=True)
            self.assertTrue(result["native_validation_fallback"])
            self.assertEqual(result["physical_receipts"], 2)
            self.assertEqual(result["reflection_items"], 0)
            feedback = self._read(root / "feedback.json")
            self.assertEqual(feedback["request_hashes"], trace)
            self.assertTrue(feedback["value"]["no_findings_reason"].startswith("posthoc_reflection_validation_failed:"))

    def _actual_salvage(self, directory, *, keep_valid):
        fixture = self._fixture(directory)
        root = self._prepare(fixture)
        first = stage.resume(root)
        self.assertEqual(first["status"], "pending_independent_role")
        pending = first["pending"][0]
        payload = json.loads(self._read(Path(pending["inbox_path"]))["messages"][-1]["content"])
        source = payload["source_catalog"][0]
        good = {"category": "plan_issues", "kind": "fact",
            "brief": "The runtime supplied a deterministic binary-correctness flag.",
            "detail": "The case source catalog provides a canonical binary outcome and preserves the original judgment.",
            "scope": {"case_refs": source["case_refs"], "plan_refs": source["plan_refs"],
                      "conditions": "For this unit case's immutable saved judgment."},
            "limitations": ["This fixture makes no causal or research-effect claim."],
            "source_refs": [source["source_ref"]], "counter_refs": [], "outcome_claims": []}
        broken = {**deepcopy(good), "brief": "Unresolvable counter-source fixture.",
                  "detail": "This offline row intentionally cites an unavailable counter-source.",
                  "counter_refs": ["reflection_source:unit-unknown"]}
        items = [good, broken] if keep_valid else [broken]
        self._answer(root, pending, {"reflection_items": items, "selected_reflection_refs": [], "no_findings_reason": None})
        trace = [pending["request_hash"]]
        second = stage.resume(root)
        self.assertEqual(second["status"], "pending_independent_role")
        pending = second["pending"][0]
        self.assertEqual(pending["stage"], "blind_predictor_posthoc_reflect_correction")
        repair = json.loads(self._read(Path(pending["inbox_path"]))["messages"][-1]["content"])
        invalid_index = 1 if keep_valid else 0
        self._answer(root, pending, {"base_hash": repair["output_patch_contract"]["base_hash"],
            "operations": [{"op": "replace", "path": f"reflection_items[{invalid_index}].counter_refs[0]",
                            "value": "reflection_source:unit-still-unknown"}]})
        trace.append(pending["request_hash"])
        raw_before = {path: path.read_bytes() for path in (root / "exchange/outbox").glob("*.txt")}
        captured, emitted = [], []
        native_reflect = stage.LLMBlindPredictor.reflect

        def reflect(predictor, *args, **kwargs):
            observer = predictor.caller.on_progress

            def witness(event):
                emitted.append(deepcopy(dict(event)))
                if observer is not None:
                    observer(event)

            predictor.caller.on_progress = witness
            step = native_reflect(predictor, *args, **kwargs)
            captured.append(step)
            return step

        with patch.object(stage.LLMBlindPredictor, "reflect", new=reflect):
            result = stage.resume(root)
        self.assertEqual(result["status"], "feedback_persisted_requires_independent_review")
        self.assertEqual(result["physical_receipts"], 2)
        self.assertEqual(len(captured), 1)
        feedback = self._read(root / "feedback.json")
        self.assertEqual(feedback["value"], captured[0].value.to_dict())
        if keep_valid:
            self.assertIsNone(captured[0].value.no_findings_reason)
        self.assertEqual(feedback["metadata"], dict(captured[0].metadata))
        self.assertEqual(feedback["usage"], asdict(captured[0].usage))
        self.assertEqual(feedback["request_hashes"], trace)
        self.assertEqual(feedback["request_trace"], [
            {"request_hash": trace[0], "stage": "blind_predictor_posthoc_reflect"},
            {"request_hash": trace[1], "stage": "blind_predictor_posthoc_reflect_correction"}])
        self.assertEqual(raw_before, {path: path.read_bytes() for path in raw_before})
        self.assertTrue(result["native_validation_fallback"])
        self.assertTrue(feedback["native_validation_fallback"])
        native_fallback = [event for event in emitted if event["event_type"] in {
            "structured_validation_fallback_applied", "deterministic_fallback_promoted", "posthoc_reflection_validation_failed"}]
        self.assertTrue(any(event["event_type"] == "structured_validation_fallback_applied" for event in native_fallback))
        self.assertEqual(feedback["native_validation_fallback_events"], native_fallback)
        prefixes = ("structured_correction", "structured_validation", "mechanical_",
                    "deterministic_fallback", "posthoc_reflection_validation")
        self.assertEqual(feedback["validation_events"], [event for event in emitted if event["event_type"].startswith(prefixes)])
        self.assertEqual(feedback["value"]["source_snapshot"], {
            "source_identity": feedback["value"]["source_identity"],
            "candidate_judgment_feedback": payload["candidate_judgment_feedback"],
            "magnitude_feedback": payload["magnitude_feedback"]})
        applied = next(event for event in native_fallback if event["event_type"] == "structured_validation_fallback_applied")
        self.assertIn(f"reflection_items[{invalid_index}]", applied["removed_paths"])
        self.assertEqual(applied["correction_count"], 1)
        return feedback, good

    def test_native_partial_salvage_flags_fallback_when_valid_sibling_has_no_reason(self):
        with tempfile.TemporaryDirectory() as directory:
            feedback, good = self._actual_salvage(directory, keep_valid=True)
            self.assertNotIn("no_findings_reason", feedback["value"])
            retained = feedback["value"]["reflection_items"]
            self.assertEqual(len(retained), 1)
            self.assertEqual({field: retained[0][field] for field in good}, good)

    def test_native_all_invalid_salvage_stays_distinct_from_honest_no_findings(self):
        with tempfile.TemporaryDirectory() as directory:
            feedback, _good = self._actual_salvage(directory, keep_valid=False)
            self.assertEqual(feedback["value"]["reflection_items"], [])
            self.assertTrue(feedback["value"]["no_findings_reason"].startswith("reflection_items_all_invalid_salvaged:"))
