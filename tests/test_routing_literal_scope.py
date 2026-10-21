"""Literal routing partitions and actual, evidence-owned residual consumption."""

from dataclasses import replace
from datetime import datetime, timezone
from unittest import TestCase

from stock_opportunity_agent.artifacts import canonical_json_hash
from stock_opportunity_agent.models import StructuredValidationError
from stock_opportunity_agent.research.evolution_core import (
    ResearchEvidenceRef, ResearchState, SignalSelectionDecision,
)
from stock_opportunity_agent.research.evolution_plan_roles import LLMSignalRetrievalAgent
from stock_opportunity_agent.research.evolution_research_validation import (
    _literal_need_partition, _shared_distinctive_phrase, _validate_research_state_refs,
)
from stock_opportunity_agent.signal_library import (
    FrozenSignalRegistry, SignalBatchResult, SignalCoverage, SignalEvidence,
    SignalResult, SignalSpec, SignalValue,
)
from tests.evolution_runtime_test_support import ScriptedRoleCaller, signal_selection


OBJECT_TARGET = (
    "What Orion Data binding offtake commitments and Aurora Sensor binding "
    "offtake commitments were disclosed by 2025-05-30?"
)
OBJECT_REASON = "Check Orion Data binding offtake commitments for named counterparties and delivery schedules."
OBJECT_RESIDUAL = "Using disclosures available by 2025-05-30, establish Aurora Sensor binding offtake commitments."
WINDOW_TARGET = (
    "What binding offtake commitments for carbon capture module were disclosed "
    "within the 180-day window ending at prediction time, and what still-effective "
    "binding offtake commitments were disclosed before that window?"
)
WINDOW_REASON = "Check binding offtake commitments for carbon capture module disclosed within the 180-day window ending at prediction time."
WINDOW_RESIDUAL = "Using disclosures available by 2025-05-30, establish still-effective binding offtake commitments for carbon capture module disclosed before the 180-day window."
DATE_TARGET = (
    "What carbon capture module binding offtake commitments were disclosed from "
    "2025-01-01 through 2025-05-30, and what still-effective binding offtake "
    "commitments were disclosed before 2025-01-01?"
)
DATE_REASON = "Check carbon capture module binding offtake commitments disclosed from 2025-01-01 through 2025-05-30."
DATE_RESIDUAL = "Using disclosures available by 2025-05-30, establish still-effective carbon capture module binding offtake commitments disclosed before 2025-01-01."


class RoutingLiteralScopeTests(TestCase):
    """Pure definitions and scripted replies exercise the native parser."""

    def registry(self):
        spec = SignalSpec.from_dict({
            "signal_id": "contract_confirmation", "version": 1, "category": "orders",
            "modality": "narrative", "definition": {"description": "Identify binding offtake commitments."},
            "execution": {"type": "llm", "skill_file": "skill.md"},
            "raw_retrieval": {"source_types": ["filing"], "lookback_days": 180},
            "evidence_policy": {"require_source": True, "require_timestamp": True, "require_exact_span": True},
        })
        return FrozenSignalRegistry(1, canonical_json_hash(spec.to_dict()), (spec,), {spec.ref: "Read contracts."})

    def select(self, target, reason, residual, **overrides):
        row = signal_selection("contract_confirmation:v1")
        row["selections"][0].update(selection_reason=reason, answer_scope="partial", residual_need=residual, **overrides)
        caller = ScriptedRoleCaller([row, row])
        agent = LLMSignalRetrievalAgent(caller)
        agent.set_evaluation_context(datetime(2025, 5, 30, tzinfo=timezone.utc))
        step = agent.select((target,), self.registry(), {})
        return step.value[0], caller

    def positives(self):
        return (
            (OBJECT_TARGET, OBJECT_REASON, OBJECT_RESIDUAL),
            (WINDOW_TARGET, WINDOW_REASON, WINDOW_RESIDUAL),
            (
                OBJECT_TARGET.replace("Orion Data", "optical sensor").replace("Aurora Sensor", "carbon capture module"),
                OBJECT_REASON.replace("Orion Data", "carbon capture module"),
                OBJECT_RESIDUAL.replace("Aurora Sensor", "optical sensor"),
            ),
            (DATE_TARGET, DATE_REASON, DATE_RESIDUAL),
            (WINDOW_TARGET, "Check binding offtake commitments disclosed within the 180-day window ending at prediction time for carbon capture module.", WINDOW_RESIDUAL),
        )

    def test_five_complete_target_partitions_keep_first_answer(self):
        for target, reason, residual in self.positives():
            with self.subTest(reason=reason):
                self.assertTrue(_literal_need_partition(target, reason, residual))
                self.assertIsNone(_shared_distinctive_phrase(reason, residual, target_need=target))
                result, caller = self.select(target, reason, residual)
                self.assertEqual(len(caller.calls), 1)
                self.assertEqual((result.reason_code, result.answer_scope, result.residual_need),
                                 ("answer_need", "partial", residual))

    def test_object_scope_needs_complete_local_whole_word_arms(self):
        reasons = (
            OBJECT_REASON.replace("Orion Data", "Aurora Sensor"),
            OBJECT_REASON + " Also measures Aurora Sensor binding offtake commitments.",
            "Check binding offtake commitments. Orion Data identifies the document title.",
            "Check binding offtake commitments. This is not an Orion Data measurement.",
            OBJECT_REASON.replace("Orion Data", "Orion Database"),
            "The document title is Orion Data binding offtake commitments.",
            "Check the document title: Orion Data binding offtake commitments.",
        )
        for reason in reasons:
            with self.subTest(reason=reason):
                self.assertFalse(_literal_need_partition(OBJECT_TARGET, reason, OBJECT_RESIDUAL))
                selected, caller = self.select(OBJECT_TARGET, reason, OBJECT_RESIDUAL)
                self.assertEqual(len(caller.calls), 2)
                self.assertNotEqual(selected.reason_code, "answer_need")

    def test_modifier_or_full_residual_does_not_prove_different_object(self):
        controls = (
            (OBJECT_TARGET.replace("Aurora Sensor", "Orion Data material"),
             OBJECT_RESIDUAL.replace("Aurora Sensor", "Orion Data material")),
            (OBJECT_TARGET, OBJECT_RESIDUAL.replace("Aurora Sensor", "Orion Data")),
            (OBJECT_TARGET, OBJECT_RESIDUAL.replace("Aurora Sensor", "Orion Data binding offtake commitments and Aurora Sensor")),
        )
        for target, residual in controls:
            with self.subTest(residual=residual):
                self.assertFalse(_literal_need_partition(target, OBJECT_REASON, residual))
                selected, _caller = self.select(target, OBJECT_REASON, residual)
                self.assertNotEqual(selected.reason_code, "answer_need")

    def test_shortened_common_heads_outside_answered_span_still_conflict(self):
        for head in ("commitments", "binding commitments", "offtake commitments"):
            for join in (" Also measures ", " and measures "):
                reason = OBJECT_REASON.rstrip(".") + join + head + "."
                with self.subTest(reason=reason):
                    self.assertFalse(_literal_need_partition(OBJECT_TARGET, reason, OBJECT_RESIDUAL))
                    result, _caller = self.select(OBJECT_TARGET, reason, OBJECT_RESIDUAL)
                    self.assertNotEqual(result.reason_code, "answer_need")

    def test_complete_objects_can_share_a_descriptor_but_not_a_modifier_only(self):
        target = OBJECT_TARGET.replace("Orion Data", "North optical module").replace("Aurora Sensor", "North capture unit")
        reason = OBJECT_REASON.replace("Orion Data", "North optical module")
        residual = OBJECT_RESIDUAL.replace("Aurora Sensor", "North capture unit")
        self.assertTrue(_literal_need_partition(target, reason, residual))
        result, caller = self.select(target, reason, residual)
        self.assertEqual(len(caller.calls), 1)
        self.assertEqual(result.residual_need, residual)
        for bad in (reason + " Also measures North capture unit binding offtake commitments.",
                    reason + " Also measures commitments."):
            with self.subTest(reason=bad):
                self.assertFalse(_literal_need_partition(target, bad, residual))
                selected, _caller = self.select(target, bad, residual)
                self.assertNotEqual(selected.reason_code, "answer_need")
        subset_target = target.replace("North capture unit", "North optical module material")
        subset_residual = residual.replace("North capture unit", "North optical module material")
        self.assertFalse(_literal_need_partition(subset_target, reason, subset_residual))

    def test_scope_must_modify_disclosure_not_delivery_or_another_sentence(self):
        for reason in (
            WINDOW_REASON.replace("disclosed within", "with deliveries within"),
            "Check binding offtake commitments for carbon capture module. The 180-day window ending at prediction time is the market-chart display period.",
            WINDOW_REASON + " Also check binding offtake commitments disclosed before that window.",
            "Check binding offtake commitments for carbon capture module.",
        ):
            with self.subTest(reason=reason):
                self.assertFalse(_literal_need_partition(WINDOW_TARGET, reason, WINDOW_RESIDUAL))
                result, _caller = self.select(WINDOW_TARGET, reason, WINDOW_RESIDUAL)
                self.assertNotEqual(result.reason_code, "answer_need")

    def test_nonoverlap_is_not_enough_when_target_middle_range_is_lost(self):
        for target, reason, residual in (
            (WINDOW_TARGET, WINDOW_REASON.replace("180-day", "90-day"), WINDOW_RESIDUAL),
            (DATE_TARGET, DATE_REASON.replace("2025-01-01", "2025-05-01"), DATE_RESIDUAL),
            (WINDOW_TARGET, WINDOW_REASON, WINDOW_RESIDUAL.replace("before the 180-day window", "within the 90-day window ending at prediction time")),
            (DATE_TARGET, DATE_REASON, DATE_RESIDUAL.replace("before 2025-01-01", "from 2025-03-01 through 2025-05-30")),
        ):
            with self.subTest(reason=reason, residual=residual):
                self.assertFalse(_literal_need_partition(target, reason, residual))
                result, _caller = self.select(target, reason, residual)
                self.assertNotEqual(result.reason_code, "answer_need")

    def test_same_words_cannot_scramble_residual_facet_and_object(self):
        residual = WINDOW_RESIDUAL.replace(
            "binding offtake commitments for carbon capture module",
            "binding offtake module for carbon capture commitments",
        )
        self.assertFalse(_literal_need_partition(WINDOW_TARGET, WINDOW_REASON, residual))
        selected, caller = self.select(WINDOW_TARGET, WINDOW_REASON, residual)
        self.assertEqual(len(caller.calls), 2)
        self.assertNotEqual(selected.reason_code, "answer_need")

    def test_independent_pit_and_typed_scope_gates_still_reject(self):
        future = "Establish Aurora Sensor binding offtake commitments disclosed after 2025-05-30, including June 2025 actual disclosures."
        selected, _caller = self.select(OBJECT_TARGET, OBJECT_REASON, future)
        self.assertNotEqual(selected.reason_code, "answer_need")
        with self.assertRaises((StructuredValidationError, TypeError, ValueError)):
            self.select(OBJECT_TARGET, OBJECT_REASON, OBJECT_RESIDUAL, target_need_indices=[True])


class ActualLiteralPartialConsumerTests(TestCase):
    """Only an actual partial with adopted available evidence can narrow needs."""

    cutoff = {"prediction_time": "2025-05-30T00:00:00+00:00"}

    def fixture(self, target=DATE_TARGET, reason=DATE_REASON, residual=DATE_RESIDUAL):
        other = "What customer qualification progress was disclosed?"
        prior = ResearchState(hypotheses=("Disclosure may affect funding.",), next_information_needs=(target, other))
        literal = "Carbon capture module disclosed binding offtake commitments on 2025-04-15."
        result = SignalResult(
            signal_id="contract_confirmation", version=1, value=SignalValue.POSITIVE,
            confidence=0.7, interpretation="contract_confirmation=positive", coverage=SignalCoverage.SUFFICIENT,
            supporting_evidence=(SignalEvidence(document_id="synthetic-body", exact_span=literal,
                                                timestamp=datetime(2025, 5, 29, tzinfo=timezone.utc)),),
        )
        ref = {"signal_ref": result.ref, "evidence_group": "supporting", "evidence_index": 0}
        state = replace(prior, next_information_needs=(residual, other), supporting_evidence=(ResearchEvidenceRef(kind="signal", claim=literal, **ref),))
        selection = SignalSelectionDecision(
            signal_ref=result.ref, reason_code="answer_need", selection_reason=reason,
            applicability_hypothesis="An actual disclosure may answer this indexed target.",
            expected_role="primary", context_tags=("general",), target_need_indices=(0,),
            answer_scope="partial", residual_need=residual,
        )
        row = {"need_index": 0, "answer_scope": "partial", "residual_need": residual,
               "evidence_refs": [ref], "reason": "The newly adopted literal answers only the stated scope; the remainder is unresolved."}
        return prior, state, selection, SignalBatchResult(results=(result,), signal_calls=1), row

    def validate(self, values, *, context=None):
        prior, state, selection, batch, row = values
        return _validate_research_state_refs(
            state, phase="reflect", previous_state=prior, selections=(selection,),
            batch=batch, need_dispositions=[row], evaluation_context=context or self.cutoff,
        )

    def test_actual_partial_exact_mirror_and_generic_reason_are_preserved(self):
        for target, reason, residual in RoutingLiteralScopeTests().positives():
            with self.subTest(target=target):
                values = self.fixture(target, reason, residual)
                self.assertEqual(self.validate(values), values[1])
                restored = ResearchState.from_dict(self.validate(values).to_dict())
                self.assertEqual(self.validate((values[0], restored, *values[2:])), restored)

    def test_no_batch_wrong_owner_or_modified_mirror_cannot_narrow(self):
        prior, state, selection, batch, row = self.fixture()
        variants = (
            (prior, state, selection, None, row),
            (prior, state, replace(selection, target_need_indices=(1,)), batch, row),
            (prior, replace(state, next_information_needs=(DATE_RESIDUAL + " Extra wording.", prior.next_information_needs[1])), selection, batch, row),
            (prior, replace(state, supporting_evidence=()), selection, batch, row),
            (prior, state, selection, batch, {**row, "evidence_refs": [{**row["evidence_refs"][0], "evidence_index": 99}]}),
        )
        for variant in variants:
            with self.subTest(variant=variant):
                with self.assertRaises(StructuredValidationError):
                    self.validate(variant)

    def test_unanswered_must_keep_original_and_untargeted_need(self):
        prior, state, selection, batch, row = self.fixture()
        unanswered = {**row, "answer_scope": "unanswered", "residual_need": None, "evidence_refs": []}
        preserved = replace(prior)
        self.assertEqual(self.validate((prior, preserved, selection, batch, unanswered)), preserved)
        for next_needs in ((DATE_RESIDUAL, prior.next_information_needs[1]), (DATE_TARGET,)):
            with self.subTest(next_needs=next_needs):
                with self.assertRaises(StructuredValidationError):
                    self.validate((prior, replace(prior, next_information_needs=next_needs), selection, batch, unanswered))

    def test_new_partition_exception_needs_valid_runtime_pit(self):
        prior, state, selection, batch, row = self.fixture()
        for instant in (datetime(2025, 5, 31, tzinfo=timezone.utc),):
            evidence = replace(batch.results[0].supporting_evidence[0], timestamp=instant)
            future = replace(batch.results[0], supporting_evidence=(evidence,))
            with self.assertRaises(StructuredValidationError):
                self.validate((prior, state, selection, replace(batch, results=(future,)), row))
        with self.assertRaises(StructuredValidationError):
            self.validate((prior, state, selection, batch, row), context={"prediction_time": "invalid"})

    def test_partition_does_not_consume_an_untargeted_duplicate_occurrence(self):
        prior, state, selection, batch, row = self.fixture()
        target, other = prior.next_information_needs
        prior = replace(prior, next_information_needs=(target, target, other))
        preserved = replace(
            state, next_information_needs=(DATE_RESIDUAL, target, other),
        )
        self.assertEqual(
            self.validate((prior, preserved, selection, batch, row)), preserved,
        )
        for next_needs in (
            (DATE_RESIDUAL, other),
            (DATE_RESIDUAL, DATE_RESIDUAL, other),
        ):
            with self.subTest(next_needs=next_needs):
                with self.assertRaises(StructuredValidationError):
                    self.validate((
                        prior, replace(state, next_information_needs=next_needs),
                        selection, batch, row,
                    ))

    def test_unavailable_result_cannot_borrow_the_routing_partition(self):
        prior, state, selection, batch, row = self.fixture()
        unavailable = replace(
            batch.results[0], value=SignalValue.UNAVAILABLE,
            coverage=SignalCoverage.UNAVAILABLE, supporting_evidence=(),
            execution_status=None,
        )
        with self.assertRaises(StructuredValidationError):
            self.validate((
                prior, state, selection, replace(batch, results=(unavailable,)), row,
            ))
