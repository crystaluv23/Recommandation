"""Regression coverage for paired provenance and complete Mining experience reads."""

import json
import tempfile
import unittest
from copy import deepcopy
from pathlib import Path

from stock_opportunity_agent.artifacts import canonical_json_hash
from stock_opportunity_agent.models import ValidationError
from stock_opportunity_agent.research.cross_round_reflection import (
    prediction_observation, prediction_comparisons, validate_prediction_observation,
)
from stock_opportunity_agent.research.evolution_core import (
    CaseReflectionEvidence, MagnitudeClass, PlanMetaMemory,
)
from stock_opportunity_agent.research.evolution_reflection_memory import ReflectionMemoryIndex
from stock_opportunity_agent.research.plan_evolution import EvolutionWorkspace
from stock_opportunity_agent.research.signal_evolution import SignalEvolutionEngine
from stock_opportunity_agent.signal_library import SignalRegistry
from tests.scheme_evolution_test_support import (
    make_trajectory, make_case, EmptyMiningModel, NoChangeUpdateModel, RawInfoStore, AgentStep, AgentUsage, SEED_CATALOG,
)
from tests.test_evolution_reflection_memory import case, authored
from tests.test_mining_controller import _fixture_store, _controller, ScriptedMiningDecisionModel


def observation(*, positive=True, context=1, issuer="comparison_fixture", date=None, technical=False):
    trajectory = make_trajectory(issuer, 4.0, positive, MagnitudeClass.TWO_TO_THREE if positive else None)
    raw = trajectory.to_dict()
    raw["final_context"] = {"evidence_revision": context}
    if date:
        raw["prediction_time"] = date
    reflection = CaseReflectionEvidence.from_trajectory(trajectory, case_index=1).to_model_dict()
    if technical:
        reflection = {"technical_exclusion": {"research_attribution_allowed": False}}
    return prediction_observation(raw, case_reflection=reflection, plan_hash="a" * 64,
        origin_contract_hash="b" * 64, record_hash=canonical_json_hash(raw),
        locator="/trajectories/0", prediction_semantics_hash="c" * 64)


class CrossRoundReflectionTests(unittest.TestCase):
    def test_direction_and_magnitude_changes_preserve_both_originals_and_unknown_cause(self):
        left, right = observation(), observation(positive=False, context=2)
        pairs = prediction_comparisons([left, right])
        self.assertEqual(len(pairs), 1)
        pair = pairs[0]
        self.assertEqual(pair["classification"], "changed_canonical_input")
        self.assertEqual(pair["cause_status"], "unestablished")
        self.assertEqual((pair["left"], pair["right"]), (left, right))
        index = ReflectionMemoryIndex(); index.add_comparisons(pairs)
        item = index.directory(level="cross_round")["items"][0]
        originals = index.read_refs(item["source_refs"], role="signal_mining", max_bytes=48000)
        self.assertEqual([row["content"] for row in originals["sources"]], [left, right])
        with self.assertRaises(ValidationError):
            index.read_refs(item["source_refs"], role="predictor")

    def test_different_issuer_date_outcome_contract_and_duplicate_import_do_not_pair(self):
        left = observation()
        self.assertEqual(prediction_comparisons([left, left]), [])
        for right in (observation(issuer="other_fixture", positive=False),
                      observation(date="2025-02-01T00:00:00+00:00", positive=False)):
            self.assertEqual(prediction_comparisons([left, right]), [])
        right = observation(positive=False)
        content = {key: value for key, value in right.items() if key != "observation_ref"}
        content["outcome_contract_hash"] = "d" * 64
        right = {**content, "observation_ref": "prediction_observation:" + canonical_json_hash(content)}
        self.assertEqual(prediction_comparisons([left, right]), [])

    def test_equal_context_is_not_model_only_and_technical_failure_is_diagnostic(self):
        self.assertEqual(prediction_comparisons([observation(), observation(positive=False)])[0]["classification"],
                         "equal_canonical_input_wire_unverified")
        pair = prediction_comparisons([observation(), observation(positive=False, technical=True)])[0]
        self.assertFalse(pair["research_attribution_allowed"])
        index = ReflectionMemoryIndex(); index.add_comparisons([pair])
        self.assertEqual(index.directory(level="cross_round")["items"][0]["category"], "technical_diagnostics")

    def test_changed_observation_and_unbound_import_are_rejected(self):
        row = observation(); row["prediction"]["is_surge"] = False
        with self.assertRaises(ValidationError):
            validate_prediction_observation(row)
        with tempfile.TemporaryDirectory() as directory:
            workspace = EvolutionWorkspace(directory)
            imported = workspace.root / "slow_history"; imported.mkdir()
            manifest = {"fast_context": {"prediction_observations": [observation()]}}
            digest = canonical_json_hash(manifest)
            (imported / "manifest.json").write_text(json.dumps({"manifest": manifest, "manifest_hash": digest}))
            contract = {"slow_history_manifest_hash": digest}
            (workspace.root / "run_contract.json").write_text(json.dumps({"contract": contract,
                "contract_hash": canonical_json_hash(contract)}))
            self.assertEqual(workspace.imported_prediction_observations(), [observation()])
            contract["slow_history_manifest_hash"] = "unbound"
            (workspace.root / "run_contract.json").write_text(json.dumps({"contract": contract,
                "contract_hash": canonical_json_hash(contract)}))
            with self.assertRaises(ValidationError):
                workspace.imported_prediction_observations()

    def test_full_index_not_initial_brief_controls_directory_and_original_reads(self):
        index = ReflectionMemoryIndex()
        for number in range(100):
            row = case(f"case:{number}")
            index._cases([row], row["source_identity"])
            source = next(source for source in index.source_catalog() if row["source_identity"] in source["case_refs"])
            index.create_items([authored(source)], level="case", owner_ref=row["source_identity"])
        brief = index.brief_view(max_bytes=6000, max_items=6)
        omitted = next(row for row in index.directory(level="case")["items"] if row["item_ref"] not in brief["included_refs"])
        cases, store = _fixture_store()
        model = ScriptedMiningDecisionModel([
            {"action": "inspect_catalog", "scope": "memory", "level": "case", "cursor": 50,
             "rationale": ["Discover experience beyond the initial selected pool."]},
            {"action": "inspect_catalog", "scope": "memory", "item_refs": [omitted["item_ref"]],
             "rationale": ["Read a complete omitted experience."]},
            {"action": "inspect_catalog", "scope": "memory", "item_refs": [omitted["item_ref"]],
             "rationale": ["Revisit the same original without duplicating retained context."]},
            {"action": "inspect_manifest", "rationale": ["Confirm the evidence scope."]},
            {"action": "record_deferred", "rationale": ["Retain observations without asserting a factor."]},
        ])
        controller = _controller(store, cases, model, seed="discovery", memory_index=index,
                                 meta_memory_briefs=brief, light_action_limit=1)
        controller.run()
        self.assertEqual(model.views[0]["meta_info"]["counts"]["available"], 100)
        self.assertEqual(model.views[1]["last_action_result"]["result"]["directory"]["total"], 100)
        self.assertIn(omitted["item_ref"], model.views[-1]["memory_consumption"]["read_refs"])
        disclosed = model.views[-1]["meta_memory_disclosures"][0]["content"]
        self.assertEqual(len(model.views[-1]["meta_memory_disclosures"]), 1)
        self.assertIn("detail", disclosed["content"])
        self.assertEqual(disclosed["content"], index.read_refs([omitted["item_ref"]], role="signal_mining")["sources"][0]["content"])
        self.assertEqual(controller._light_used, 1)
        self.assertEqual(controller._browse_used, 3)
        self.assertLess(len(json.dumps(model.views[0]["meta_info"]).encode()), 14000)

    def test_production_context_preserves_completed_cross_round_layer(self):
        pair = prediction_comparisons([observation(), observation(positive=False, context=2)])[0]
        class ReflectingModel(EmptyMiningModel):
            def reflect_feedback(self, payload):
                self.reflection_payload = deepcopy(payload)
                return AgentStep({"episode_reflections": [{"episode_ref": payload["episode_slots"][0],
                    "source_refs": [pair["comparison_ref"]], "reflection": "Test whether evidence selection changes the interpretation of business catalysts.",
                    "unresolved_questions": ["The causal contribution is unestablished."],
                    "kind": "hypothesis", "brief": "Compare catalyst evidence selection under the two research plans."}],
                    "lesson_additions": []}, AgentUsage())
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); workspace = EvolutionWorkspace(root / "workspace")
            workspace.cycle_state_path.write_text(json.dumps({"run_contract_hash": "e" * 64,
                "last_completed_cycle": 0, "active_cycle": {"cycle_id": 1}}))
            imported = workspace.root / "slow_history"; imported.mkdir()
            manifest = {"schema_version": "slow-history-manifest-v2", "source_namespace": "source-fixture",
                        "committed_slow_cycle": 0, "cycle_artifacts": [], "learning_events": [],
                        "fast_context": {"prediction_observations": [pair["left"], pair["right"]]}}
            (imported / "manifest.json").write_text(json.dumps({"manifest": manifest, "manifest_hash": canonical_json_hash(manifest)}))
            contract = {"cycle_mode": "slow_only", "slow_history_manifest_hash": canonical_json_hash(manifest)}
            (workspace.root / "run_contract.json").write_text(json.dumps({"contract": contract,
                "contract_hash": canonical_json_hash(contract)}))
            registry = SignalRegistry(root / "signals"); registry.install_catalog(SEED_CATALOG)
            model = ReflectingModel()
            engine = SignalEvolutionEngine(registry=registry, raw_info_store=RawInfoStore(),
                discovery_cases=tuple(make_case(f"comparison_{i}", 4.0 if i % 2 else 1.1) for i in range(8)),
                meta_memory=PlanMetaMemory(), workspace=workspace,
                mining_model=model, update_model=NoChangeUpdateModel(), llm_signal_runner=None)
            frozen = engine._prepare_slow_input(cycle_id=1, input_snapshot=registry.freeze())
            memory = engine._prepare_slow_memory(cycle_id=1, slow_input=frozen)
            self.assertEqual(memory["episode_reflections"][0]["reflection_layer"], "cross_round")
            self.assertEqual(model.reflection_payload["feedback_units"][0]["artifact"], pair)
            engine._active_slow_input, engine._active_slow_memory = frozen, memory
            context = engine._mining_context(cycle_id=1)
            items = engine._mining_memory_index.directory(level="cross_round")["items"]
            self.assertTrue(any(row["kind"] == "hypothesis" for row in items))
            self.assertIn("Compare catalyst", json.dumps(context["slow_method_memory"]))
            before = workspace.load_slow_memory(1)
            self.assertEqual(engine._prepare_slow_memory(cycle_id=1, slow_input=frozen), before)


if __name__ == "__main__":
    unittest.main()
