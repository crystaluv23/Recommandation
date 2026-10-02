"""Committed use, target isolation, exact persistence and Slow consumption."""

from dataclasses import replace
from unittest import TestCase
from unittest.mock import patch

from stock_opportunity_agent.artifacts import canonical_json_hash
from stock_opportunity_agent.models import ValidationError
from stock_opportunity_agent.signal_library import SignalLearningEvent, SignalValue, SignalCoverage
from stock_opportunity_agent.research.signal_tracking import record_committed_signal_use, target_use_profiles
from stock_opportunity_agent.research.signal_evolution import read_slow_sources, _slow_feedback_source_catalog
from tests import test_slow_technical_admission as admission_fixture


class SignalTrackingTests(TestCase):
    def setUp(self):
        fixture = admission_fixture.SlowTechnicalAdmissionTests()
        fixture.setUp()
        self.addCleanup(fixture.doCleanups)
        self.registry = fixture.registry
        self.engine = fixture.engine
        initial = fixture.validate()
        self.registry.promote_validated_batch(initial.validated_candidates,
            validated_evaluations=initial.candidate_evaluations, transition_id="tracking-fixture",
            input_version=initial.input_registry_version, input_hash=initial.input_registry_hash,
            input_refs=initial.input_signal_refs)
        self.ref = fixture.magnitude.ref
        self.direction = fixture.update.ref

    def event(self, case, multiple, state=SignalValue.POSITIVE, plan="plan-1", round_id=1, ref=None):
        ref = ref or self.ref
        return SignalLearningEvent(event_id=canonical_json_hash([case, plan, round_id, ref, state.value]),
            observation_key=canonical_json_hash({"case_id": case, "signal_ref": ref, "document_fingerprint": [case]}),
            signal_ref=ref, round_id=round_id, plan_id=plan, case_id=case, company_id=case,
            prediction_time="2025-01-31T00:00:00+00:00",
            selection={"signal_ref": ref, "reason_code": "answer_need", "selection_reason": "Measure reported annual growth.",
                "applicability_hypothesis": "Annual periods are available.", "expected_role": "primary", "context_tags": []},
            result_value=state, coverage=SignalCoverage.SUFFICIENT, document_fingerprint=(case,),
            is_surge=multiple >= 2, realized_max_multiple=multiple, prediction_correct=True)

    def test_two_targets_dedup_population_and_no_supported_effect(self):
        high = self.event("high", 3.4)
        events = (high, self.event("high", 3.4, plan="plan-2"), self.event("low", 2.5, SignalValue.NEGATIVE),
            self.event("outside", 1.1), self.event("unavailable", 4.0, SignalValue.UNAVAILABLE),
            self.event("direction", 1.1, SignalValue.NEGATIVE, ref=self.direction))
        self.assertEqual(record_committed_signal_use(self.registry, events), 5)
        before = self.registry._target_evaluations_path().read_bytes()
        self.assertEqual(record_committed_signal_use(self.registry, events), 0)
        self.assertEqual(self.registry._target_evaluations_path().read_bytes(), before)
        magnitude = target_use_profiles(self.registry, self.ref, round_cutoff=1)["magnitude_ge3_v1"]
        self.assertEqual((magnitude["selection_events"], magnitude["physical_observations"], magnitude["eligible_observations"]), (5, 4, 3))
        self.assertEqual(magnitude["outside_population"], 1)
        self.assertEqual(magnitude["unavailable_observations"], 1)
        self.assertEqual(magnitude["mean_realized_multiple_by_state"]["positive"], 3.4)
        self.assertEqual(magnitude["state_outcome_matrix"]["negative"]["ge3_low"], 1)
        self.assertEqual(magnitude["effect_status"], "unverified")
        self.assertEqual(self.registry.target_support(self.ref, "magnitude_ge3_v1")["results"], {"inconclusive": 3, "insufficient_evidence": 1})
        direction = target_use_profiles(self.registry, self.direction, round_cutoff=1)["surge_direction"]
        self.assertEqual(direction["state_outcome_matrix"]["negative"]["non_surge"], 1)
        self.assertEqual(self.registry.load_research_status(self.ref)["effect_status"], "unverified")

    def test_cutoff_and_disputed_execution_do_not_fabricate_association(self):
        original = self.event("same-input", 3.5)
        record_committed_signal_use(self.registry, (original,))
        first = target_use_profiles(self.registry, self.ref, round_cutoff=1)
        record_committed_signal_use(self.registry, (self.event("future", 8.0, round_id=2),))
        self.assertEqual(target_use_profiles(self.registry, self.ref, round_cutoff=1), first)
        record_committed_signal_use(self.registry, (self.event("same-input", 3.5, SignalValue.NEGATIVE, plan="other"),))
        profile = target_use_profiles(self.registry, self.ref, round_cutoff=1)["magnitude_ge3_v1"]
        self.assertEqual(profile["disputed_observations"], 1)
        self.assertEqual(profile["eligible_observations"], 0)
        self.assertIsNone(profile["mean_realized_multiple_by_state"]["positive"])

    def test_atomic_derivative_recovery_and_exact_collision(self):
        event = self.event("recover", 3.8)
        with patch("stock_opportunity_agent.signal_library._atomic_write_text", side_effect=OSError("interrupted derivative write")):
            with self.assertRaises(OSError):
                record_committed_signal_use(self.registry, (event,))
        self.assertEqual(len(self.registry.load_learning_events(self.ref)), 1)
        self.assertEqual(self.registry.load_target_evaluations(self.ref), ())
        self.assertEqual(record_committed_signal_use(self.registry, (event,)), 1)
        row = self.registry.load_target_evaluations(self.ref)[0]
        before = self.registry._target_evaluations_path().read_bytes()
        with self.assertRaises(ValidationError):
            self.registry.record_target_evaluations((replace(row, evaluation_id="fresh"), replace(row, result="supported")))
        self.assertEqual(self.registry._target_evaluations_path().read_bytes(), before)
        with self.assertRaises(ValidationError):
            record_committed_signal_use(self.registry, (replace(event, realized_max_multiple=7.0),))
        self.assertEqual(self.registry._target_evaluations_path().read_bytes(), before)

    def test_slow_summary_is_actual_source_and_h1_cannot_read_outcomes(self):
        record_committed_signal_use(self.registry, (self.event("readable-source", 4.1),))
        self.engine.workspace.state_path.write_text('{"last_completed_round": 1}\n')
        rows, manifest = self.engine._committed_slow_feedback()
        units = [row for row in rows if row["kind"] == "signal_target_observation"]
        self.assertEqual(len(units), 1)
        source = next(item for item in manifest if item["ref"] == units[0]["feedback_ref"])
        self.assertNotIn("H1", source["visible_to"])
        self.assertIn("Update", source["visible_to"])
        self.assertEqual(source["content_hash"], canonical_json_hash(units[0]["artifact"]))
        self.assertEqual(units[0]["artifact"]["state_outcome_matrix"]["positive"]["ge3_high"], 1)
        self.engine._active_slow_input = {"feedback_rows": rows, "source_manifest": manifest}
        self.engine._active_slow_memory = {"processed_feedback_refs": [units[0]["feedback_ref"]]}
        self.assertEqual(self.engine._slow_method_view("H1")["source_entries"], [])
        consumed = self.engine._slow_method_view("Update")["source_entries"]
        self.assertEqual(consumed[0]["content"]["artifact"]["physical_observations"], 1)
        with self.assertRaises(ValidationError):
            read_slow_sources((units[0]["feedback_ref"],), role_scope="H1",
                source_catalog=_slow_feedback_source_catalog(rows, manifest), budget_bytes=64000)
        with self.assertRaises(ValidationError):
            _slow_feedback_source_catalog(units, ())
