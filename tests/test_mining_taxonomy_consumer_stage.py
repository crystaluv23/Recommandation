"""Native local-request reconstruction and terminal isolation for the module."""
from contextlib import contextmanager
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase
from unittest.mock import patch

import run_mining_taxonomy_consumer_stage as stage
from stock_opportunity_agent.artifacts import canonical_json_hash
from stock_opportunity_agent.cases.label_store import LabelStore
from stock_opportunity_agent.data.raw_info import RawInfoDocument, RawInfoStore
from stock_opportunity_agent.models import ValidationError
from stock_opportunity_agent.research.local_role_exchange import LocalRoleExchange


class MiningTaxonomyConsumerStageTests(TestCase):
    @contextmanager
    def prepared(self):
        with TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            sample = {"case_id": "fixture-only", "case_ref": "synthetic", "company_id": "fixture-issuer",
                "cutoff": "2024-08-02T00:00:00+00:00", "label": "control", "concept": "Metric",
                "content": json.dumps({"facts": {"us-gaap": {"Metric": {"units": {"USD": [
                    {"end": "2024-06-30", "val": 120}, {"end": "2023-06-30", "val": 100}]}}}}})}
            inputs, contract = {"namespace": sample}, {"limits": stage.LIMITS}
            manifest = {"inputs_hash": canonical_json_hash(inputs), "contract_hash": canonical_json_hash(contract),
                "source_files": [], "code_files": []}
            manifest["manifest_hash"] = canonical_json_hash(manifest)
            for name, value in (("inputs", inputs), ("contract", contract), ("manifest", manifest)):
                stage.save(root, name, value)
            with patch.object(stage, "ROOT", root), patch.object(stage, "code_bindings", return_value=[]):
                yield root

    def submit(self, root, pending, action):
        Path(pending["outbox_path"]).write_text(json.dumps(action))
        LocalRoleExchange(root / "namespace/exchange", max_calls=6).submit(
            pending["request_hash"], agent_id="explicit-offline-test-fixture")

    def test_pending_cache_reconstruction_retains_two_operands_without_double_count(self):
        with self.prepared() as root:
            pending = stage.advance("namespace")
            self.assertEqual(pending["state"], "pending")
            first_view = json.loads(next(m["content"] for m in json.loads(Path(pending["inbox_path"]).read_text())["messages"] if m["role"] == "user"))
            refs = first_view["known_fact_refs"]
            self.assertEqual(len(refs), 2)
            for ref in refs:
                self.submit(root, pending, {"action": "read_span", "fact_ref": ref, "rationale": ["Inspect fixture source."]})
                pending = stage.advance("namespace")
                self.assertEqual(pending["state"], "pending")
            self.submit(root, pending, {"action": "record_deferred", "rationale": ["Stop this fixture module."]})
            terminal = stage.advance("namespace")
            self.assertEqual(terminal["state"], "completed_module_boundary")
            boundary = json.loads((root / "namespace/boundary.json").read_text())
            page = boundary["view"]["structured_read_progress"]
            self.assertEqual({r["fact_ref"] for r in page["items"]}, set(refs))
            self.assertEqual([r["read_count"] for r in page["items"]], [1, 1])
            self.assertEqual(boundary["view"]["budget"]["heavy_remaining"], 3)
            self.assertFalse(boundary["native_domain_terminal_executed"])
            self.assertNotIn("record_deferred", [r["action"] for r in boundary["ledger"]["entries"]])
            with patch.object(stage, "make_client", side_effect=AssertionError("terminal reentry")):
                self.assertEqual(stage.advance("namespace"), terminal)
            corrupted = {**terminal, "state": "synthetic-corrupted-terminal-state"}
            (root / "namespace/completion.json").write_text(json.dumps(corrupted))
            with self.assertRaisesRegex(ValidationError, "terminal metadata"):
                stage.advance("namespace")
            corrupted["terminal_hash"] = canonical_json_hash({k: v for k, v in corrupted.items() if k != "terminal_hash"})
            (root / "namespace/completion.json").write_text(json.dumps(corrupted))
            with self.assertRaisesRegex(ValidationError, "terminal metadata"):
                stage.advance("namespace")
            (root / "namespace/completion.json").write_text(json.dumps(terminal))
            (root / "namespace/boundary.json").write_text("{}")
            with self.assertRaises(ValidationError):
                stage.advance("namespace")

    def test_forbidden_model_action_seals_failure_without_execution(self):
        with self.prepared() as root:
            pending = stage.advance("namespace")
            self.submit(root, pending, {"action": "fetch_evidence", "rationale": ["Forbidden fixture action."],
                "case_refs": ["synthetic"], "source_families": ["sec_company_facts"], "max_documents": 1})
            result = stage.advance("namespace")
            self.assertEqual(result["state"], "terminal_module_failure")
            failed = json.loads((root / "namespace/failed-controller.json").read_text())
            self.assertEqual(len(failed["ledger"]["entries"]), 1)
            self.assertEqual(failed["ledger"]["entries"][0]["action"], "fetch_evidence")
            self.assertEqual(stage.advance("namespace"), result)

    def test_effect_guards_allow_memory_constructor_but_reject_labels_and_persistent_append(self):
        with self.prepared() as root:
            from datetime import datetime, timezone
            clock = datetime(2024, 8, 2, tzinfo=timezone.utc)
            document = RawInfoDocument.create(document_id="fixture-doc", company_id="fixture-issuer",
                source_type="company_facts", published_at=clock, available_at=clock, content="{}")
            persistent = RawInfoStore(root / "not-a-source")
            with stage.guards():
                self.assertEqual(len(RawInfoStore(documents=(document,)).documents), 1)
                with self.assertRaises(stage.EffectRejected):
                    persistent.append(document)
                with self.assertRaises(stage.EffectRejected):
                    LabelStore.load(root / "forbidden")

    def test_prepare_rejects_source_or_inventory_drift_since_preflight(self):
        for mode in ("source-content", "source-added", "code-added"):
            with self.subTest(mode=mode), TemporaryDirectory() as directory:
                base = Path(directory).resolve()
                source = base / "source.json"
                source.write_text("{}")
                frozen = [stage.binding(source)]
                stage.save(base / "preflight", "result", {"code_files": [], "source_files": frozen})
                stage.save(base / "reference", "prefreeze-obligations", {})
                if mode == "source-content":
                    source.write_text('{"changed":true}')
                current = [stage.binding(source)]
                if mode == "source-added":
                    extra = base / "extra.json"
                    extra.write_text("{}")
                    current.append(stage.binding(extra))
                code = [stage.binding(source)] if mode == "code-added" else []
                with patch.object(stage, "BASE", base), patch.object(stage, "ROOT", base / "stage"), \
                     patch.object(stage, "authorities", return_value=({}, current)), \
                     patch.object(stage, "code_bindings", return_value=code):
                    with self.assertRaises(ValidationError):
                        stage.prepare()
                self.assertFalse((base / "stage").exists())

    def test_native_input_only_enforces_single_request_and_prepared_call_caps(self):
        with self.prepared() as root, stage.guards():
            sample = json.loads((root / "inputs.json").read_text())["namespace"]
            oversized_root = root / "oversized"
            client = stage.make_client(oversized_root, sample, {"limits": stage.LIMITS}, input_only=True)
            controller = stage.build_controller(oversized_root, sample, client)
            view = controller._model_view()
            view["explicit_offline_size_fixture"] = "长" * 11000
            with self.assertRaisesRegex(stage.LocalRoleBudgetExhausted, "single-request"):
                controller.model.next_action(view)
            self.assertFalse(list(oversized_root.rglob("inbox/*.json")))
            count_root = root / "count"
            client = stage.make_client(count_root, sample, {"limits": stage.LIMITS}, input_only=True)
            view = controller._model_view()
            for index in range(7):
                view["explicit_offline_distinct_request"] = index
                error = stage.InputCaptured if index < 6 else stage.LocalRoleBudgetExhausted
                with self.assertRaises(error):
                    client.complete_json(stage="mining_controller_step", system_prompt="Offline size probe.",
                        payload=view, allow_outcomes=True, max_output_tokens=32)
            self.assertFalse(list(count_root.rglob("inbox/*.json")))
            self.assertEqual(len(list((count_root / "requests").glob("*.json"))), 6)
