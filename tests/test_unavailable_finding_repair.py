"""Unavailable coverage findings use exact owner-authorized State quarantine."""

from copy import deepcopy
from datetime import datetime, timezone
from unittest import TestCase

from stock_opportunity_agent.models import StructuredValidationError, ValidationIssue
from stock_opportunity_agent.research.evolution_core import (
    ResearchEvidenceRef, ResearchState, default_information_plan,
)
from stock_opportunity_agent.research.evolution_output_validation import (
    _research_state_evidence_grounding_fallback,
)
from stock_opportunity_agent.research.evolution_plan_roles import LLMResearchController
from stock_opportunity_agent.research.repair import is_mechanical_issue
from stock_opportunity_agent.signal_library import (
    SignalBatchResult, SignalCoverage, SignalExecutionStatus, SignalResult, SignalValue,
)
from tests.evolution_runtime_test_support import ScriptedRoleCaller


class UnavailableFindingRepairTests(TestCase):
    """Exercise the production Controller, its complete validator and repair ladder."""

    BAD = "Customer concentration is unavailable, so its coverage remains unknown."
    RESOLUTION = "Customer concentration resolves as unavailable in the visible evidence."

    def prior(self):
        claim = "The issuer disclosed commercial expansion."
        return ResearchState(
            hypotheses=("Commercial expansion may change expectations.",),
            current_beliefs=(claim,),
            supporting_evidence=(ResearchEvidenceRef(
                kind="basic_info", claim=claim, projection_id="projection-expansion",
                exact_text=claim,
            ),),
            resolved_questions=("Commercial expansion was disclosed.",),
            next_information_needs=(
                "What customer concentration was disclosed by the prediction time?",
                "What financing was disclosed by the prediction time?",
            ),
        )

    def batch(self, status=SignalExecutionStatus.DOMAIN_UNAVAILABLE):
        unavailable = status is not SignalExecutionStatus.SUCCESS
        technical = status not in (
            SignalExecutionStatus.SUCCESS, SignalExecutionStatus.DOMAIN_UNAVAILABLE,
        )
        return SignalBatchResult(results=(SignalResult(
            signal_id="customer_concentration", version=1,
            value=SignalValue.UNAVAILABLE if unavailable else SignalValue.NEUTRAL,
            confidence=0 if unavailable else 0.5,
            coverage=SignalCoverage.UNAVAILABLE if unavailable else SignalCoverage.SUFFICIENT,
            interpretation="Observed coverage.", execution_status=status,
            execution_error_code="fixture_failure" if technical else None,
            execution_error_message="Fixture technical diagnostic." if technical else None,
        ), SignalResult(
            signal_id="financing_disclosure", version=1, value=SignalValue.NEUTRAL,
            confidence=0.5, interpretation="No binding financing change was disclosed.",
        )), signal_calls=2)

    def reflect(self, value, *, status=SignalExecutionStatus.DOMAIN_UNAVAILABLE,
                terminal=False, extra_outputs=()):
        caller = ScriptedRoleCaller([value, *extra_outputs])
        controller = LLMResearchController(caller)
        controller.set_evaluation_context(datetime(2025, 9, 30, tzinfo=timezone.utc))
        controller.reflection_must_finalize = terminal
        step = controller.reflect(default_information_plan(), self.prior(), self.batch(status))
        return step, caller

    def invalid(self):
        value = self.prior().to_dict()
        value["current_beliefs"].append(self.BAD)
        value["resolved_questions"].append(self.RESOLUTION)
        return value

    def test_all_unavailable_causes_preserve_prior_state_without_paid_correction(self):
        for status in SignalExecutionStatus:
            if status is SignalExecutionStatus.SUCCESS:
                continue
            with self.subTest(status=status):
                value = self.invalid()
                original = deepcopy(value)
                step, caller = self.reflect(value, status=status)
                self.assertEqual(step.value, self.prior())
                self.assertEqual(len(caller.calls), 1)
                self.assertEqual(step.usage.llm_calls, 1)
                self.assertEqual(value, original)

    def test_terminal_decision_is_model_authored_and_survives_exact_quarantine(self):
        value = self.invalid()
        value["decision"] = "finalize"
        step, caller = self.reflect(value, terminal=True)
        expected = self.prior().to_dict()
        expected["decision"] = "finalize"
        self.assertEqual(step.value.to_dict(), expected)
        self.assertEqual(len(caller.calls), 1)

    def test_duplicate_members_share_one_snapshot_and_keep_valid_siblings(self):
        value = self.invalid()
        value["current_beliefs"] += ["Commercial demand remains uncertain.", self.BAD]
        value["resolved_questions"] += ["The filing date is known.", self.RESOLUTION]
        # Continue permits available unrelated observations while preserving both needs.
        step, caller = self.reflect(value)
        self.assertEqual(step.value.current_beliefs, (
            *self.prior().current_beliefs, "Commercial demand remains uncertain.",
        ))
        self.assertEqual(step.value.resolved_questions, (
            *self.prior().resolved_questions, "The filing date is known.",
        ))
        self.assertEqual(step.value.next_information_needs, self.prior().next_information_needs)
        self.assertEqual(step.value.supporting_evidence, self.prior().supporting_evidence)
        self.assertEqual(len(caller.calls), 1)

    def test_available_topic_and_unchanged_prior_findings_are_not_quarantined(self):
        value = self.prior().to_dict()
        value["current_beliefs"].append("Customer concentration remains unassessed.")
        step, caller = self.reflect(value, status=SignalExecutionStatus.SUCCESS)
        self.assertEqual(step.value.to_dict(), value)
        self.assertEqual(len(caller.calls), 1)
        # Prior coverage wording remains prior state, rather than a new resolution.
        prior_value = self.prior().to_dict()
        prior_value["resolved_questions"].append(self.RESOLUTION)
        prior = ResearchState.from_dict(prior_value)
        caller = ScriptedRoleCaller([prior_value])
        step = LLMResearchController(caller).reflect(default_information_plan(), prior, self.batch())
        self.assertEqual(step.value, prior)

    def issue(self, **overrides):
        fields = dict(
            code="unavailable_signal_treated_as_finding", message="No prose authority.",
            paths=("current_beliefs[1]",), allowed_repairs=("remove",),
            repair_context={
                "mechanical_action": "remove_unavailable_finding",
                "unavailable_finding_field": "current_beliefs",
                "unavailable_finding_text": self.BAD,
                "unavailable_signal_ref": "customer_concentration:v1",
            },
        )
        fields.update(overrides)
        return ValidationIssue(**fields)

    def test_quarantine_requires_exact_typed_member_and_remove_authority(self):
        value = self.invalid()
        variants = [
            {"paths": ("current_beliefs",)},
            {"paths": ("resolved_questions[1]",)},
            {"paths": ("current_beliefs[9]",)},
            {"paths": ("current_beliefs[0]",)},
            {"allowed_repairs": ("replace",)},
            {"allowed_repairs": ("add",)},
            {"allowed_repairs": ("replace", "remove")},
            {"dependent_paths": ("decision",)},
            {"path_policy": "any"},
            {"repair_context": {}},
            {"repair_context": {**self.issue().repair_context, "unavailable_signal_ref": ""}},
        ]
        for variant in variants:
            with self.subTest(variant=variant):
                self.assertIsNone(_research_state_evidence_grounding_fallback(
                    value, StructuredValidationError([self.issue(**variant)]),
                ))
        candidate, actions = _research_state_evidence_grounding_fallback(
            value, StructuredValidationError([self.issue()]),
        )
        expected = deepcopy(value)
        del expected["current_beliefs"][1]
        self.assertEqual(candidate, expected)
        self.assertEqual(actions["removed_paths"], ("current_beliefs[1]",))
        self.assertEqual(value, self.invalid())
        self.assertTrue(is_mechanical_issue(self.issue()))
        self.assertFalse(is_mechanical_issue(self.issue(repair_context={})))

    def test_full_parser_does_not_accept_a_separate_future_information_failure(self):
        value = self.invalid()
        value["decision"] = "finalize"
        future_need = "What metrics did the issuer provide in its Q3 earnings, reported in November 2025?"
        value["next_information_needs"].append(future_need)
        # The normal correction removes the future question; full revalidation
        # must then discover and quarantine the separate unavailable findings.
        corrected = self.invalid()
        corrected["decision"] = "finalize"
        step, caller = self.reflect(value, terminal=True, extra_outputs=(corrected,))
        expected = self.prior().to_dict()
        expected["decision"] = "finalize"
        self.assertEqual(step.value.to_dict(), expected)
        self.assertEqual(len(caller.calls), 2)
        failed = caller.calls[1]["payload"]["validation_feedback"]["invalid_output"]
        # The temporal normalizer rejects first; no unavailable-topic authority
        # exists until the corrected snapshot reaches the complete State parser.
        self.assertIn(self.BAD, failed["current_beliefs"])
        self.assertIn(self.RESOLUTION, failed["resolved_questions"])
        self.assertIn(future_need, failed["next_information_needs"])
