"""Production Slow admission with upstream staged-output fixtures, not effect gates."""

from dataclasses import replace
from copy import deepcopy
from datetime import datetime
from pathlib import Path
import tempfile
from unittest import TestCase
from types import SimpleNamespace
from unittest.mock import patch

from stock_opportunity_agent.data.raw_info import RawInfoDocument, RawInfoStore
from stock_opportunity_agent.models import ValidationError
from stock_opportunity_agent.research.evolution_core import PlanMetaMemory, ResearchState
from stock_opportunity_agent.research.evolution_plan_roles import LLMSignalRetrievalAgent, LLMResearchController
from stock_opportunity_agent.research.plan_evolution import EvolutionWorkspace
from stock_opportunity_agent.research.signal_evolution import SignalEvolutionEngine
from stock_opportunity_agent.signal_library import SignalExecutor, SignalRegistry
from tests.evolution_runtime_test_support import ScriptedRoleCaller
from tests.scheme_evolution_test_support import (
    SEED_CATALOG, EmptyMiningModel, NoChangeUpdateModel, candidate_growth_fixture, make_case, default_information_plan,
)


class SlowTechnicalAdmissionTests(TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        root = Path(self.directory.name)
        self.registry = SignalRegistry(root / "signals")
        self.registry.install_catalog(SEED_CATALOG)
        current = self.registry.load_spec("revenue_growth_yoy:v1")
        self.update = replace(current, version=2, parameters={**current.parameters, "positive_min": .15})
        self.magnitude = replace(current, signal_id="magnitude_revenue_measurement", version=1,
            description="Measure annual revenue growth with a contrasting positive threshold.",
            parameters={**current.parameters, "positive_min": .22})
        self.invalid = replace(self.magnitude, signal_id="invalid_revenue_measurement",
            description="Measure annual revenue growth with an incompatible fixture threshold.",
            parameters={**current.parameters, "positive_min": .9})
        self.duplicate = replace(self.magnitude, signal_id="duplicate_revenue_measurement",
            description="Another name for the same annual revenue growth threshold measurement.")
        for spec in (self.update, self.magnitude, self.invalid, self.duplicate):
            self.registry.stage_candidate(spec, skill=None, tests=(candidate_growth_fixture(),), origin="fixture:staged-output")
        self.engine = SignalEvolutionEngine(registry=self.registry, raw_info_store=RawInfoStore(),
            discovery_cases=(make_case("admission-positive", 4.0), make_case("admission-control", 1.1)), meta_memory=PlanMetaMemory(), workspace=EvolutionWorkspace(root / "workspace"),
            mining_model=EmptyMiningModel(), update_model=NoChangeUpdateModel(), llm_signal_runner=None)
        self.mining = {"candidate_refs": (self.magnitude.ref, self.invalid.ref, self.duplicate.ref),
            "induction_case_ids": {}, "validation_case_ids": {}, "refined_hypotheses": {}, "failures": {}, "audit": {},
            "candidate_research_targets": {self.magnitude.ref: "magnitude_ge3_v1", self.invalid.ref: "surge_direction"}}
        self.updating = {"candidate_refs": (self.update.ref,), "induction_case_ids": {}, "validation_case_ids": {}, "failures": {}, "audit": {}}

    def validate(self):
        with patch.object(self.engine, "_run_signal_mining", return_value=self.mining), patch.object(self.engine, "_run_signal_update", return_value=self.updating):
            return self.engine._validate_cycle(self.registry.freeze(), cycle_id=1)

    def test_direction_magnitude_update_admit_without_observations_but_invalids_reject(self):
        with patch.object(self.engine.effectiveness_evaluator, "evaluation_identity", side_effect=AssertionError("No admission effect I/O")), patch.object(self.engine.effectiveness_evaluator, "evaluate", side_effect=AssertionError("No admission effect I/O")):
            result = self.validate()
        self.assertEqual(set(result.validated_candidates), {self.update.ref, self.magnitude.ref})
        self.assertIn(self.invalid.ref, result.rejected)
        self.assertIn(self.duplicate.ref, result.rejected)
        self.assertEqual(result.provisional_candidates, {})
        self.assertEqual(result.candidate_effectiveness[self.magnitude.ref]["status"], "pending_use")
        self.assertNotIn("candidate", result.candidate_effectiveness[self.magnitude.ref])
        transition = self.registry.promote_validated_batch(result.validated_candidates,
            validated_evaluations=result.candidate_evaluations, transition_id="two-axes-admission",
            input_version=result.input_registry_version, input_hash=result.input_registry_hash, input_refs=result.input_signal_refs)
        self.assertEqual(set(transition.promoted), {self.update.ref, self.magnitude.ref})
        self.assertEqual(self.registry.freeze().research_status[self.magnitude.ref]["research_targets"], ["magnitude_ge3_v1"])

    def test_passing_technical_checkpoint_reused_without_fixture_regeneration(self):
        self.validate()
        original = self.engine.validator.validate
        refs = []
        def validate(spec, **kwargs):
            refs.append(spec.ref)
            return original(spec, **kwargs)
        with patch.object(self.engine.validator, "validate", side_effect=validate):
            self.validate()
        self.assertNotIn(self.magnitude.ref, refs)
        self.assertNotIn(self.update.ref, refs)
        self.assertIn(self.invalid.ref, refs)

    def test_original_authoring_lineage_survives_admission_and_later_cycles(self):
        self.engine._active_slow_input = {"cycle_id": 1, "source": "frozen-input"}
        with patch.object(self.engine, "_current_generation_case_ids", return_value=("authoring-case",)):
            result = self.validate()
        key = result.candidate_evaluations[self.magnitude.ref]
        original = self.registry.load_candidate_validation(self.magnitude.ref, evaluation_key=key)["admission_identity"]["research_provenance"]
        self.assertEqual(original["generation_case_ids"], ["authoring-case"])
        self.assertEqual(original["origin"], "current_cycle")
        self.engine._active_slow_input = {"cycle_id": 2}
        self.assertEqual(self.engine._candidate_research_provenance(self.magnitude.ref,
            target_id="magnitude_ge3_v1", induction_case_ids=("later-case",)), original)
        self.assertIn("authoring-case", self.engine._candidate_evaluation_exclusions(
            self.magnitude.ref, target_id="magnitude_ge3_v1"))
        self.registry.promote_validated_batch(result.validated_candidates,
            validated_evaluations=result.candidate_evaluations, transition_id="lineage",
            input_version=result.input_registry_version, input_hash=result.input_registry_hash, input_refs=result.input_signal_refs)
        restored = SignalRegistry(self.registry.root).freeze()
        self.assertNotIn("research_provenance", restored.research_status[self.magnitude.ref])

    def test_magnitude_version_update_inherits_purpose_without_inheriting_effect(self):
        initial = self.validate()
        self.registry.promote_validated_batch(initial.validated_candidates,
            validated_evaluations=initial.candidate_evaluations, transition_id="initial-purpose",
            input_version=initial.input_registry_version, input_hash=initial.input_registry_hash, input_refs=initial.input_signal_refs)
        next_version = replace(self.magnitude, version=2, parameters={**self.magnitude.parameters, "positive_min": .18})
        self.registry.stage_candidate(next_version, skill=None, tests=(candidate_growth_fixture(),), origin="fixture:update")
        self.mining = {**self.mining, "candidate_refs": (), "candidate_research_targets": {}}
        self.updating = {**self.updating, "candidate_refs": (next_version.ref,)}
        result = self.validate()
        self.assertIn(next_version.ref, result.validated_candidates)
        self.assertEqual(result.candidate_effectiveness[next_version.ref]["research_targets"], ["magnitude_ge3_v1"])
        self.assertEqual(result.candidate_effectiveness[next_version.ref]["effect_status"], "unverified")

    def test_effect_failure_and_completed_evidence_never_change_admission(self):
        result = self.validate()
        admission_key = result.candidate_evaluations[self.magnitude.ref]
        before = self.registry.load_candidate_validation(self.magnitude.ref)
        failure = self.registry.record_candidate_effectiveness(self.magnitude.ref, admission_key=admission_key,
            evaluation_identity=None, observation_status="failed", effectiveness={"status": "failed", "error": "No independent cohort"})
        identity = {name: "b" * 64 for name in ("baseline_hash", "cohort_hash", "source_manifest_hash", "projection_hash", "validator_hash", "model_hash", "sampling_hash")}
        completed = self.registry.record_candidate_effectiveness(self.magnitude.ref, admission_key=admission_key,
            evaluation_identity=identity, effectiveness={"accepted": False, "disposition": "provisional", "reasons": ["Sparse independent evidence"]})
        self.assertNotEqual(failure, completed)
        self.assertEqual(self.registry.load_candidate_validation(self.magnitude.ref), before)
        self.assertEqual(len(self.registry.list_candidate_effectiveness(self.magnitude.ref)), 2)
        for row in self.registry.list_candidate_effectiveness(self.magnitude.ref):
            self.assertEqual(row["admission_key"], admission_key)
        with self.assertRaises(ValidationError):
            self.registry.record_candidate_effectiveness(self.invalid.ref,
                admission_key=self.registry.load_candidate_validation(self.invalid.ref)["evaluation_key"],
                evaluation_identity=identity, effectiveness={"accepted": True})

    def test_actual_selector_and_reflect_payload_disclose_current_version_status(self):
        result = self.validate()
        self.registry.promote_validated_batch(result.validated_candidates,
            validated_evaluations=result.candidate_evaluations, transition_id="model-status",
            input_version=result.input_registry_version, input_hash=result.input_registry_hash, input_refs=result.input_signal_refs)
        snapshot = self.registry.freeze()
        need = "What annual revenue growth was reported by 2025-01-31?"
        selection = {"selections": [{"signal_ref": self.magnitude.ref, "reason_code": "answer_need",
            "selection_reason": "Measure annual revenue growth.", "applicability_hypothesis": "Comparable annual periods exist.",
            "expected_role": "primary", "context_tags": ["comparable_financials"], "target_need_indices": [0],
            "answer_scope": "full", "residual_need": None}]}
        caller = ScriptedRoleCaller([selection])
        selector = LLMSignalRetrievalAgent(caller)
        selector.select((need,), snapshot, {}, eligible_signal_refs=(self.magnitude.ref,))
        card = caller.calls[0]["payload"]["available_signal_cards"][0]
        deepcopy(caller.calls[0]["payload"])
        self.assertEqual(card["research_status"]["effect_status"], "unverified")
        self.assertEqual(card["research_status"]["research_targets"], ["magnitude_ge3_v1"])
        fixture = candidate_growth_fixture()
        raw = fixture["documents"][0]
        document = RawInfoDocument.create(document_id="status-fixture", company_id="status-issuer",
            source_type=raw["source_type"], published_at=datetime.fromisoformat(raw["published_at"]),
            available_at=datetime.fromisoformat(raw["available_at"]), content=raw["content"])
        batch = SignalExecutor(snapshot, RawInfoStore(documents=(document,))).execute_batch((self.magnitude.ref,),
            company_id="status-issuer", as_of=datetime.fromisoformat(fixture["as_of"]))
        def finalize(request):
            return {"base_hash": request["payload"]["output_patch_contract"]["base_hash"],
                "operations": [{"op": "replace", "path": "decision", "value": "finalize"}]}
        reflect_caller = ScriptedRoleCaller([finalize])
        controller = LLMResearchController(reflect_caller)
        controller.set_signal_research_status(snapshot.research_status)
        controller.set_document_channel(SimpleNamespace(catalog_view=lambda: {}))
        controller.reflect(default_information_plan(), ResearchState(hypotheses=("Measure reported growth.",), next_information_needs=(need,)), batch)
        sent = reflect_caller.calls[0]["payload"]["signal_research_status"]
        self.assertEqual(set(sent), {self.magnitude.ref})
        self.assertEqual(sent[self.magnitude.ref]["effect_status"], "unverified")
        sent[self.magnitude.ref]["research_targets"].append("view-only")
        card["research_status"]["research_targets"].append("view-only")
        self.assertEqual(snapshot.research_status[self.magnitude.ref]["research_targets"], ["magnitude_ge3_v1"])
        with self.assertRaises(TypeError):
            snapshot.research_status[self.magnitude.ref]["research_targets"].append("immutable")
