"""Pre-cutoff event agendas and future realized findings have distinct scopes."""

from datetime import date, datetime, timezone
from unittest import TestCase

from stock_opportunity_agent.research.evolution_core import ResearchState, default_information_plan
from stock_opportunity_agent.research.evolution_plan_roles import LLMResearchController
from stock_opportunity_agent.research.evolution_research_validation import _future_source_date_refs
from tests.evolution_runtime_test_support import ScriptedRoleCaller


VALID_NEED = (
    "What did the issuer disclose by the prediction time about the scheduled "
    "November 7, 2025 third-quarter results webcast, including any stated expectations, "
    "guidance ranges, or business-update topics it planned to address?"
)
INVALID_NEED = (
    "What specific third-quarter 2025 financial results and business update did the issuer "
    "disclose on November 7, 2025, including revenue, earnings, and any changes to full-year guidance?"
)


class ScheduledResultsMetadataTests(TestCase):
    def refs(self, text):
        return _future_source_date_refs(text, date(2025, 9, 30), field_name="next_information_needs")

    def test_schedule_and_declared_agenda_variations_are_pre_cutoff_questions(self):
        for event in ("webcast", "call", "conference", "presentation", "release"):
            with self.subTest(event=event):
                self.assertEqual(self.refs(VALID_NEED.replace("webcast", event)), [])
                self.assertEqual(self.refs(
                    f"What did management disclose by 2025-09-30 about the planned November 7, 2025 "
                    f"results {event}, including topics it planned to address?"), [])
                self.assertEqual(self.refs(
                    f"What was the expected scope of the November 7, 2025 results {event}, "
                    "as of the prediction time?"), [])

    def test_actual_findings_contents_later_publications_and_missing_cutoffs_reject(self):
        invalid = [INVALID_NEED, VALID_NEED.replace("by the prediction time ", ""),
            VALID_NEED.replace("by the prediction time", "as of November 8, 2025"),
            VALID_NEED[:-1] + " and what were the actual financial results?",
            "What revenue was reported at the scheduled November 7, 2025 results webcast, as of September 30, 2025?",
            "What were the contents of the scheduled November 7, 2025 results webcast, as of September 30, 2025?",
            "What did the issuer disclose by the prediction time about the timing of its results webcast published on November 7, 2025?",
            "What actual results were discussed at the planned November 7, 2025 results call, as of September 30, 2025?"]
        for text in invalid:
            with self.subTest(text=text):
                self.assertTrue(self.refs(text))

    def test_controller_scoped_correction_accepts_agenda_without_changing_siblings(self):
        invalid = ResearchState(next_information_needs=(INVALID_NEED,), decision="continue").to_dict()
        corrected = {**invalid, "next_information_needs": [VALID_NEED]}
        caller = ScriptedRoleCaller([invalid, corrected])
        controller = LLMResearchController(caller)
        controller.set_evaluation_context(datetime(2025, 9, 30, tzinfo=timezone.utc))
        result = controller.initialize(default_information_plan(), {"requests": []})
        self.assertEqual(result.value.next_information_needs, (VALID_NEED,))
        self.assertEqual(len(caller.calls), 2)
        self.assertEqual(result.value.to_dict(), corrected)
