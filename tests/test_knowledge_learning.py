"""Knowledge card boundaries, explicit consumption and committed lifecycle tests."""

import json
import tempfile
from dataclasses import replace
from pathlib import Path
from unittest import TestCase

from stock_opportunity_agent.artifacts import atomic_write_json, canonical_json_hash
from stock_opportunity_agent.memory.knowledge import KnowledgeUseStore, usage_context, use_performance, knowledge_observations
from stock_opportunity_agent.models import ValidationError
from stock_opportunity_agent.research.evolution_core import InformationPlan
from stock_opportunity_agent.research.evolution_core import PlanMetaMemory, RoundMetaEntry, default_information_plan
from stock_opportunity_agent.research.evolution_plan_roles import LLMInformationPlanProposer, LLMSignalRetrievalAgent
from stock_opportunity_agent.signal_library import SignalRegistry
from stock_opportunity_agent.research.evolution_reflection_memory import ReflectionMemoryIndex
from tests.test_evolution_reflection_memory import authored, case
from tests.scheme_evolution_test_support import make_record
from tests.evolution_runtime_test_support import ScriptedRoleCaller


class KnowledgeContextTests(TestCase):
    def test_context_unknown_and_invalid_versions(self):
        self.assertIsNone(usage_context()["when_to_use"])
        with self.assertRaises(ValidationError):
            usage_context({"when_to_use": "When demand recovers", "failure_conditions": [], "related_refs": ["growth"]})

    def test_experience_signal_index_is_sourced_and_original_identity_is_stable(self):
        index = ReflectionMemoryIndex.from_case_rows([case()], owner_ref="case:a")
        source = index.source_catalog()[0]
        value = authored(source)
        value["related_signal_refs"] = ["growth:v1"]
        with self.assertRaises(ValidationError):
            index.create_items([value], level="case", owner_ref="case:a")
        value.pop("related_signal_refs")
        item = index.create_items([value], level="case", owner_ref="case:a")[0]
        brief = index.brief_view()["items"][0]
        self.assertEqual(brief["usage_context"]["when_to_use"], value["scope"]["conditions"])
        self.assertEqual(brief["usage_context"]["failure_conditions"], value["limitations"])
        original = index.read_refs([item.item_ref], role="proposer")["sources"][0]["content"]
        self.assertEqual(original, item.to_dict())
        self.assertNotIn("usage_context", original)

    def test_plan_adoption_survives_persistence_without_changing_strategy(self):
        record = make_record("plan_a", 1.0, (1.0,))
        plan = replace(record.plan, experience_usage={"snapshot_hash": "a" * 64, "item_refs": ["reflection:" + "b" * 64]})
        self.assertEqual(plan.canonical_dict(), record.plan.canonical_dict())
        self.assertEqual(InformationPlan.from_dict(plan.to_dict()), plan)
        self.assertNotIn("experience_usage", record.plan.to_dict())

    def test_signal_index_returns_only_linked_experiences(self):
        snapshot = {**case(), "signal_usage": {"growth:v1": {"executed": True}}}
        index = ReflectionMemoryIndex.from_case_rows([snapshot], owner_ref="case:a")
        source = next(row for row in index.source_catalog() if "growth:v1" in row.get("signal_refs", ()))
        value = authored(source)
        value["related_signal_refs"] = ["growth:v1"]
        linked = index.create_items([value], level="case", owner_ref="case:a")[0]
        other = authored(index.source_catalog()[0])
        other["brief"] = "A different unrelated lesson."
        index.create_items([other], level="case", owner_ref="case:a")
        self.assertEqual([row["item_ref"] for row in index.directory(signal_ref="growth:v1")["items"]], [linked.item_ref])
        self.assertEqual(index.directory(signal_ref="growth:v2")["items"], [])


class KnowledgeCommitTests(TestCase):
    def commit(self, root, record):
        atomic_write_json(root / "plans" / record.plan_id / "record.json", record.to_dict())
        checkpoint = {"round_id": record.round_id, "plan_ids": [record.plan_id], "run_contract_hash": "contract"}
        atomic_write_json(root / "experiments" / f"round-{record.round_id:04d}" / "checkpoint.json", checkpoint)
        atomic_write_json(root / "state.json", {"last_completed_round": record.round_id})

    def test_staged_rows_are_hidden_and_missing_derivative_recovers(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            record = make_record("plan_a", 1.0, (1.0,))
            store = KnowledgeUseStore(root)
            store.record(record.to_dict(), contract_hash="contract")
            self.assertEqual(store.committed_rows(), ())
            self.commit(root, record)
            rows = store.committed_rows()
            self.assertEqual(len(rows), 1)
            self.assertIsNone(rows[0]["experience_refs"])
            for path in (root / "knowledge" / "observations").glob("*.json"):
                path.unlink()
            self.assertEqual(KnowledgeUseStore(root).committed_rows(), rows)
            self.assertEqual(store.committed_rows(round_cutoff=0), ())

    def test_derivative_cannot_forge_source_outcomes(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            record = make_record("plan_a", 1.0, (1.0,))
            self.commit(root, record)
            store = KnowledgeUseStore(root)
            store.committed_rows(repair=True)
            path = next((root / "knowledge" / "observations").glob("*.json"))
            value = json.loads(path.read_text())
            value["rows"][0]["predicted"] = False
            row = value["rows"][0]
            row["event_id"] = canonical_json_hash({key: val for key, val in row.items() if key != "event_id"})
            atomic_write_json(path, value)
            with self.assertRaisesRegex(ValidationError, "canonical source"):
                store.committed_rows()

    def test_import_requires_contract_and_preserves_transitive_observation_identity(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            record = make_record("plan_a", 1.0, (1.0,))
            rows = knowledge_observations(record.to_dict(), contract_hash="source")
            manifest = {"knowledge_observations": rows}
            digest = canonical_json_hash(manifest)
            atomic_write_json(root / "slow_history" / "manifest.json", {"manifest_hash": digest, "manifest": manifest})
            self.assertEqual(KnowledgeUseStore(root).committed_rows(), ())
            contract = {"slow_history_manifest_hash": digest}
            atomic_write_json(root / "run_contract.json", {"contract": contract, "contract_hash": canonical_json_hash(contract)})
            self.assertEqual(KnowledgeUseStore(root).committed_rows(), tuple(rows))
            manifest["knowledge_observations"][0]["predicted"] = False
            atomic_write_json(root / "slow_history" / "manifest.json", {"manifest_hash": digest, "manifest": manifest})
            with self.assertRaises(ValidationError):
                KnowledgeUseStore(root).committed_rows()


class KnowledgePerformanceTests(TestCase):
    ref = "reflection:" + "b" * 64

    def rows(self):
        record = make_record("plan_a", 1.0, (1.0,))
        record = replace(record, plan=replace(record.plan,
            experience_usage={"snapshot_hash": "a" * 64, "item_refs": [self.ref]}))
        return knowledge_observations(record.to_dict(), contract_hash="contract")

    def test_repeats_have_one_case_weight_and_unknown_is_not_zero(self):
        row = self.rows()[0]
        wrong = {**row, "predicted": False}
        profile = use_performance([row, row, row, wrong], self.ref)
        self.assertEqual(profile["independent_cases"], 1)
        self.assertEqual(profile["evaluated_predictions"], 2)
        self.assertEqual(profile["correct_rate"], 0.5)
        self.assertEqual(profile["confusion"]["tp"], 0.5)
        self.assertEqual(profile["confusion"]["fn"], 0.5)
        self.assertIsNone(profile["negative_case_correct_rate"])
        self.assertIsNone(use_performance([], self.ref)["correct_rate"])

    def test_technical_exclusion_cannot_receive_negative_success_credit(self):
        row = {**self.rows()[0], "actual": False, "predicted": False, "technical": True}
        profile = use_performance([row], self.ref)
        self.assertEqual(profile["technical_cases"], 1)
        self.assertEqual(profile["evaluated_cases"], 0)
        self.assertEqual(profile["confusion"]["tn"], 0)
        self.assertIsNone(profile["correct_rate"])

    def test_profile_is_in_brief_and_directory_without_mutating_original(self):
        index = ReflectionMemoryIndex.from_case_rows([case()], owner_ref="case:a")
        item = index.create_items([authored(index.source_catalog()[0])], level="case", owner_ref="case:a")[0]
        row = {**self.rows()[0], "experience_refs": [item.item_ref]}
        updated = ReflectionMemoryIndex(performance_profiles={item.item_ref: use_performance([row], item.item_ref)})
        updated._item(item)
        self.assertEqual(updated.brief_view()["items"][0]["performance"]["correct_rate"], 1.0)
        self.assertEqual(updated.directory()["items"][0]["performance"]["independent_cases"], 1)
        original = updated.read_refs([item.item_ref], role="proposer")["sources"][0]["content"]
        self.assertNotIn("performance", original)

    def test_immutable_outcome_conflict_is_not_hidden_by_dedup(self):
        row = self.rows()[0]
        with self.assertRaisesRegex(ValidationError, "immutable outcomes"):
            use_performance([row, {**row, "actual": False}], self.ref)

    def test_class_breakdown_exposes_false_positives_and_negatives(self):
        positive = self.rows()[0]
        negative = {**positive, "case_key": "another-case", "issuer_key": "another-issuer",
                    "actual": False, "predicted": True}
        profile = use_performance([positive, negative], self.ref)
        self.assertEqual(profile["correct_rate"], 0.5)
        self.assertEqual(profile["positive_case_correct_rate"], 1.0)
        self.assertEqual(profile["negative_case_correct_rate"], 0.0)
        self.assertEqual(profile["unique_issuers"], 2)
        self.assertEqual(profile["confusion"]["fp"], 1.0)

    def test_signal_unavailable_and_conflicting_measurements_receive_no_credit(self):
        row = {**self.rows()[0], "signal_refs": ["growth:v1"], "invalid_signal_refs": [],
               "signal_observations": [{"signal_ref": "growth:v1", "input_key": "same-input",
                                        "state": "positive", "coverage": "full"}]}
        conflict = {**row, "signal_observations": [{**row["signal_observations"][0], "state": "negative"}]}
        profile = use_performance([row, conflict], "growth:v1")
        self.assertEqual(profile["disputed_cases"], 1)
        self.assertIsNone(profile["correct_rate"])
        unavailable = {**row, "signal_refs": [], "invalid_signal_refs": ["growth:v1"]}
        profile = use_performance([unavailable], "growth:v1")
        self.assertEqual(profile["unavailable_cases"], 1)
        self.assertIsNone(profile["correct_rate"])


class KnowledgeConsumerTests(TestCase):
    def test_actual_proposer_sees_profile_and_persists_adopted_reference(self):
        memory = PlanMetaMemory(entries=(RoundMetaEntry(round_id=1,
            search_implications=("Check cash conversion when reported growth accelerates.",),
            evidence_refs=("plan_old",)),))
        index = memory.reflection_index()
        ref = index.brief_view()["included_refs"][0]
        parent = default_information_plan()
        output = {"B": parent.basic_info_policy.to_dict(), "H_init": parent.initial_research_skill,
            "H_reflect": parent.reflection_skill + " Inspect cash conversion counterevidence.",
            "H_analyse": parent.analysis_prompt, "used_experience_refs": [ref]}
        caller = ScriptedRoleCaller([output])
        proposer = LLMInformationPlanProposer(caller)
        proposer.set_experience_profiles({ref: {"correct_rate": 0.6, "independent_cases": 10}})
        plan = proposer.propose(round_id=2, candidate_index=1, candidate_count=1,
            proposal_attempt=2, forbidden_plan_ids=(), parents=(parent,),
            meta_info=memory.entries, prior="fixed research prior")
        self.assertEqual(plan.experience_usage["item_refs"], (ref,))
        items = caller.calls[0]["payload"]["proposal_context"]["meta_info"]["items"]
        self.assertEqual(items[0]["performance"]["correct_rate"], 0.6)
        self.assertEqual(InformationPlan.from_dict(plan.to_dict()), plan)

    def test_signal_brief_and_selector_have_same_committed_performance(self):
        from tests.scheme_evolution_test_support import SEED_CATALOG, SyntheticPlanEvaluator
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            registry = SignalRegistry(root / "signals")
            registry.install_catalog(SEED_CATALOG)
            # Exercise canonical nested Signal serialization, not a fabricated flat result.
            from tests.scheme_evolution_test_support import make_evaluation_pool
            trajectory = SyntheticPlanEvaluator().evaluate(default_information_plan(),
                make_evaluation_pool(), registry.freeze())[0]
            record = make_record("plan_a", 1.0, (1.0,))
            from stock_opportunity_agent.research.evolution_core import PlanEvaluationSummary, score_predictions
            record = replace(record, trajectories=(trajectory,), metrics=score_predictions([trajectory]),
                evaluation=PlanEvaluationSummary(evaluation_stage="round", n_cases=1,
                    case_ids=(trajectory.case_id,), dataset_snapshot_ids=("snapshot",)), fitness=None,
                knowledge_signal_refs=tuple(spec.ref for spec in registry.freeze().specs))
            KnowledgeCommitTests().commit(root, record)
            profile = KnowledgeUseStore(root).profiles()
            signal_ref = next(iter(record.trajectories[0].signal_rounds[0].batch.results)).ref
            self.assertEqual(profile[signal_ref]["correct_rate"], 1.0)
            card = next(card for card in registry.list_signal_cards() if card.ref == signal_ref)
            self.assertEqual(card.to_dict()["performance"], profile[signal_ref])
            frozen = registry.freeze()
            self.assertEqual(frozen.learned_profiles[signal_ref]["performance"], profile[signal_ref])
            self.assertEqual(registry.freeze(learning_round_cutoff=0).learned_profiles[signal_ref]["performance"]["independent_cases"], 0)
            caller = ScriptedRoleCaller([{"selections": []}])
            LLMSignalRetrievalAgent(caller).select(("Investigate an unmatched research question.",), frozen, {})
            cards = caller.calls[0]["payload"]["available_signal_cards"]
            disclosed = next(card for card in cards if card["signal_ref"] == signal_ref)
            self.assertEqual(disclosed["performance"], profile[signal_ref])
            self.assertIn("usage_context", disclosed)

    def test_two_committed_rounds_refresh_proposer_and_restore_full_history(self):
        from tests.scheme_evolution_test_support import (
            CountingProposer, SimpleCritic, SimpleRoundReflector, SyntheticPlanEvaluator,
            SEED_CATALOG, make_evaluation_pool, make_anchor_pool,
        )
        from stock_opportunity_agent.research.plan_evolution import EvolutionWorkspace, PlanEvolutionEngine
        from stock_opportunity_agent.research.evolution_core import PlanArchive
        memory = PlanMetaMemory(maxlen=1, entries=(RoundMetaEntry(round_id=-1,
            search_implications=("Check cash conversion before accepting growth.",), evidence_refs=("seed",)),))
        ref = memory.brief_view()["included_refs"][0]

        class AdoptingProposer(CountingProposer):
            def __init__(self):
                super().__init__()
                self.snapshots = []

            def set_experience_profiles(self, profiles):
                self.snapshots.append(profiles)

            def propose(self, **kwargs):
                return replace(super().propose(**kwargs),
                    experience_usage={"snapshot_hash": "a" * 64, "item_refs": [ref]})

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            registry = SignalRegistry(root / "signals")
            registry.install_catalog(SEED_CATALOG)
            workspace = EvolutionWorkspace(root / "workspace")
            proposer = AdoptingProposer()
            engine = PlanEvolutionEngine(archive=PlanArchive(), meta_memory=memory,
                signal_registry=registry, evaluator=SyntheticPlanEvaluator(), proposer=proposer,
                critic=SimpleCritic(), round_reflector=SimpleRoundReflector(), workspace=workspace,
                seed_plans=(default_information_plan(),), candidates_per_round=1)
            for round_id in (1, 2):
                engine.run_round(round_id=round_id, validation_cases=make_evaluation_pool(),
                    anchor_cases=make_anchor_pool(), signal_snapshot=registry.freeze())
            self.assertEqual(proposer.snapshots[0], {})
            self.assertEqual(proposer.snapshots[1][ref]["correct_rate"], 1.0)
            profile = memory.experience_profiles[ref]
            # Sixteen shared anchors plus rotating Random cases across rounds.
            self.assertEqual(profile["independent_cases"], 32)
            self.assertEqual(len(memory.entries), 1)
            self.assertNotIn(ref, memory.brief_view()["included_refs"])
            restored = workspace.restore_meta(maxlen=1)
            self.assertEqual(restored.experience_profiles[ref], profile)
            before = KnowledgeUseStore(workspace.root).profiles(round_cutoff=1, publish=False)
            self.assertEqual(before[ref]["independent_cases"], 24)
