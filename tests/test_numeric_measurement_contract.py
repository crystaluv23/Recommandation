"""Producer-owned measurements survive actual stage parsing and local repairs."""

from copy import deepcopy
from dataclasses import replace
from datetime import datetime, timezone
import json
from unittest import TestCase

from stock_opportunity_agent.data.raw_info import RawInfoDocument
from stock_opportunity_agent.llm.agent import AgentUsage
from stock_opportunity_agent.models import StructuredValidationError, ValidationError
from stock_opportunity_agent.research.evolution_output_validation import (
    _measurement_reasoning_issues, _blind_prediction_from_role, _compact_posthoc_context,
)
from stock_opportunity_agent.research.evolution_plan_roles import LLMBlindPredictor
from stock_opportunity_agent.research.evolution_research_validation import _signal_batch_model_view, _validate_research_state_refs
from stock_opportunity_agent.research.evolution_signal_roles import StructuredLLMSignalRunner
from stock_opportunity_agent.signal_library import (
    NumericMeasurement, SignalResult, SignalSpec, SignalExecutionType, SignalModality,
    SignalValue, SignalBatchResult, SignalEvidence, default_deterministic_signal_functions,
    signal_result_model_view, validate_signal_result,
)
from stock_opportunity_agent.research.evolution_core import GroundTruth, ResearchState
from tests.test_evolution_state_patch import PatchCaller, patch

AS_OF = datetime(2025, 2, 1, tzinfo=timezone.utc)


def financial_product(signal_id="gross_margin_change", function="financial.gross_margin_change"):
    """Use the real calculator on literal same-duration, same-currency facts."""
    facts = []
    for start, end, revenue, profit, flow in (
        ("2023-07-01", "2023-12-31", 100, 50, 10),
        ("2024-07-01", "2024-12-31", 200, 80, -20),
    ):
        for tag, number in (("Revenues", revenue), ("GrossProfit", profit),
                            ("NetCashProvidedByUsedInOperatingActivities", flow)):
            facts.append({"tag": tag, "unit": "USD", "start": start, "end": end, "value": number})
    facts += [{"tag": "CashAndCashEquivalentsAtCarryingValue", "unit": "USD", "end": "2024-12-31", "value": 50},
              {"tag": "LiabilitiesCurrent", "unit": "USD", "end": "2024-12-31", "value": 100}]
    content = json.dumps({"schema_version": "sec-company-facts-document-v1", "filing_date": "2025-01-20", "form": "10-K", "facts": facts}, sort_keys=True, separators=(",", ":"))
    document = RawInfoDocument.create(document_id="facts", company_id="issuer", source_type="sec_company_facts",
        published_at=AS_OF, available_at=AS_OF, content=content)
    spec = SignalSpec(signal_id=signal_id, version=1, category="financial", description="Reported measurement.",
        execution_type=SignalExecutionType.DETERMINISTIC, modality=SignalModality.STRUCTURED,
        function=function, source_types=("sec_company_facts",), parameters={"positive_min": 1, "negative_max": 1})
    result = default_deterministic_signal_functions()[function](spec, (document,), AS_OF)
    validate_signal_result(spec, result, (document,), as_of=AS_OF)
    return spec, document, result


def prediction():
    return {"candidate_judgment": "unlikely", "magnitude": None,
            "confidence": {"level": "medium"}, "session_id": "anonymous",
            "key_reasons": ["Source-backed operating uncertainty."],
            "uncertainties": ["Gross margin change was -10.0% (negative).", "Keep this sibling exactly."]}


def context(result):
    return {"signal_rounds": [{"batch": {"results": [result.to_dict()]}}]}


class NumericMeasurementContractTests(TestCase):
    def test_calculator_owns_units_for_arbitrary_signal_identity(self):
        _, _, result = financial_product("custom_margin_delta")
        self.assertAlmostEqual(result.measurement.value, -0.1)
        self.assertEqual(result.measurement.unit, "fraction_difference")
        self.assertEqual(result.measurement.period_start, "2024-07-01")
        self.assertEqual(result.measurement.period_end, "2024-12-31")
        self.assertEqual(result.interpretation, "gross_margin_change=-0.1")
        self.assertEqual(SignalResult.from_dict(result.to_dict()), result)

    def test_model_view_keeps_sign_state_period_and_exact_claim_distinct(self):
        _, _, result = financial_product("liquidity_ratio", "financial.cash_to_current_liabilities_ratio")
        self.assertEqual(result.value, SignalValue.NEGATIVE)
        view = signal_result_model_view(result)
        numeric = view["interpretation"]["measurement_context"]["numeric_measurement"]
        self.assertEqual((numeric["value"], numeric["numeric_sign"], numeric["categorical_state"]), (0.5, "positive", "negative"))
        self.assertEqual(numeric["unit"], "ratio")
        reflected = _signal_batch_model_view(SignalBatchResult((result,), 1))[0]
        self.assertEqual(reflected["measurement_context"], view["interpretation"]["measurement_context"])
        self.assertEqual(reflected["exact_claim_if_adopted"], result.interpretation)
        self.assertNotIn("measurement_context", result.to_dict()["interpretation"])

    def test_legacy_result_does_not_gain_fabricated_metadata(self):
        _, _, result = financial_product()
        legacy = result.to_dict(); legacy.pop("measurement")
        self.assertEqual(SignalResult.from_dict(legacy).to_dict(), legacy)
        self.assertNotIn("numeric_measurement", signal_result_model_view(legacy)["interpretation"]["measurement_context"])
        self.assertEqual(_measurement_reasoning_issues((("text", "Gross margin change was -10%."),), (legacy,)), [])

    def test_numeric_schema_and_cited_period_fail_closed(self):
        _, _, result = financial_product()
        for change in ({"value": True}, {"value": float("inf")}, {"value": 0.5, "unit": "count"}, {"value": -1, "unit": "months"}, {"unit": []}, {"unit": "percent"},
                       {"formula": ""}, {"period_end": "2025-2-1"},
                       {"period_start": "2025-01-01", "period_end": "2024-12-31"}):
            args = {"value": 0.1, "unit": "ratio", "formula": "a / b", **change}
            with self.subTest(change=change), self.assertRaises(ValidationError): NumericMeasurement(**args)
        for period in ({}, {"end": None}, {"start": "2024-01-01"}):
            with self.subTest(period=period), self.assertRaises(ValidationError):
                NumericMeasurement.from_dict({"value": 0.1, "unit": "ratio", "formula": "a / b", "period": period})
        spec, document, _ = financial_product()
        with self.assertRaisesRegex(ValidationError, "disagrees"):
            replace(result, measurement=replace(result.measurement, value=0.1))
        corrupted = replace(result, measurement=replace(result.measurement, period_start="2024-01-01"))
        with self.assertRaisesRegex(ValidationError, "cited source"):
            validate_signal_result(spec, corrupted, (document,), as_of=AS_OF)

    def test_unit_guard_is_local_and_preserves_scenarios_other_windows_and_versions(self):
        _, _, result = financial_product()
        raw = result.to_dict()
        bad = _measurement_reasoning_issues((("uncertainties[2]", "Gross margin change was -10.0% (negative), so execution may be constrained."),), (raw,))
        self.assertEqual(bad[0].paths, ("uncertainties[2]",))
        self.assertEqual(bad[0].source_refs, (result.ref,))
        from stock_opportunity_agent.research.evolution_output_validation import _exact_value_fallback
        stale = {"uncertainties": ["one", "two", "Different text."]}
        self.assertIsNone(_exact_value_fallback(stale, StructuredValidationError(bad)))
        matching = {"uncertainties": ["one", "two", bad[0].repair_context["original_text"]]}
        self.assertIsNone(_exact_value_fallback(matching, StructuredValidationError([replace(bad[0], allowed_repairs=("remove",))])))
        fixed, _ = _exact_value_fallback(matching, StructuredValidationError(bad))
        self.assertEqual(fixed["uncertainties"][:2], matching["uncertainties"][:2])
        self.assertIn("-10.0 percentage points", fixed["uncertainties"][2])
        for text in ("Gross margin change was -10.0 percentage points.", "Gross margin change=-0.1.",
                     "Gross margin change could reach -10% next year.", "Projected gross margin change is -10%.",
                     "Gross margin change was not -10%.", "Gross margin change was -10% is incorrect.",
                     "Gross margin change was observed. Revenue fell -10%.", "Revenue growth was -10%.",
                     "Gross margin change was -20% in another comparison window."):
            self.assertEqual(_measurement_reasoning_issues((("text", text),), (raw,)), [], text)
        other = deepcopy(raw); other["version"] = 2
        self.assertEqual(_measurement_reasoning_issues((("text", "Gross margin change was -10%."),), (raw, other)), [])

    def test_predictor_repairs_only_the_proved_member(self):
        _, _, result = financial_product()
        original = prediction()
        def repair(call):
            self.assertEqual(call["payload"]["required_change_paths"], ["uncertainties[0]"])
            return patch(call["payload"]["output_patch_contract"], {"op": "replace", "path": "uncertainties[0]",
                         "value": "Gross margin change was -10.0 percentage points (negative)."})
        caller = PatchCaller(original, repair)
        value = LLMBlindPredictor(caller).predict(context(result)).value
        self.assertEqual(value.key_reasons, tuple(original["key_reasons"]))
        self.assertEqual(value.uncertainties[1], original["uncertainties"][1])
        self.assertEqual(value.candidate_judgment.value, "unlikely")
        self.assertIn("percentage points", caller.calls[0]["system_prompt"])
        self.assertEqual(len(caller.calls), 1)

    def test_reflection_receives_metadata_and_revalidates_exact_detail(self):
        _, _, result = financial_product()
        original = prediction(); original["uncertainties"][0] = "Gross margin change was -10 percentage points."
        packet = context(result)
        self.assertEqual(_compact_posthoc_context(packet)["signal_results"][0]["measurement"], result.measurement.to_dict())
        def initial(call):
            source = call["payload"]["source_catalog"][0]
            return {"reflection_items": [{"category": "missing_information", "kind": "hypothesis",
              "brief": "Review margin evidence.", "detail": "Gross margin change was -10.0% (negative).",
              "scope": {"case_refs": source["case_refs"], "plan_refs": source["plan_refs"], "conditions": "Reported source period."},
              "limitations": ["Not a causal conclusion."], "source_refs": [source["source_ref"]], "counter_refs": [], "outcome_claims": []}],
              "selected_reflection_refs": [], "no_findings_reason": None}
        def repair(call):
            self.assertEqual(call["payload"]["required_change_paths"], ["reflection_items[0].detail"])
            return patch(call["payload"]["output_patch_contract"], {"op": "replace", "path": "reflection_items[0].detail",
                         "value": "Gross margin change was -10.0 percentage points (negative)."})
        caller = PatchCaller(initial, repair)
        reflected = LLMBlindPredictor(caller).reflect(packet, _blind_prediction_from_role(original), GroundTruth(1.1)).value
        self.assertIn("percentage points", reflected.reflection_items[0].detail)
        self.assertEqual(reflected.reflection_items[0].brief, "Review margin evidence.")
        self.assertEqual(len(caller.calls), 1)

    def test_research_guard_authorizes_only_invalid_prose(self):
        _, _, result = financial_product()
        state = ResearchState(hypotheses=("Review source.",), current_beliefs=("Gross margin change was -10.0%.",),
                              next_information_needs=("Review reported context.",), decision="continue")
        with self.assertRaises(StructuredValidationError) as caught:
            _validate_research_state_refs(state, phase="reflect", previous_state=state, batch=SignalBatchResult((result,), 1))
        issues = [i for i in caught.exception.issues if i.code == "numeric_measurement_unit_invalid"]
        self.assertEqual(issues[0].paths, ("current_beliefs[0]",))
        self.assertEqual(issues[0].allowed_repairs, ("replace", "remove"))

    def test_actual_final_assembly_retains_metadata_through_posthoc_projection(self):
        from stock_opportunity_agent.research.evolution_core import (
            _assemble_final_context, default_information_plan, SignalRound, SignalSelectionDecision,
        )
        from stock_opportunity_agent.research.evolution_output_validation import _context_signal_results
        _, _, result = financial_product()
        selection = SignalSelectionDecision(result.ref, "answer_need", "Read observed margin.",
                                              "Reported matched periods.", "primary", ("general",), (0,), "full")
        state = ResearchState(decision="finalize")
        assembled = _assemble_final_context(plan=default_information_plan(), company_id="issuer",
            additional_identity_aliases=(), basic_info={"requests": []}, state=state,
            rounds=(SignalRound(("Read margin.",), (selection,), SignalBatchResult((result,), 1)),), prediction_time=AS_OF)
        card = assembled["signal_rounds"][0]["batch"]["results"][0]
        self.assertNotIn("signal_id", card)
        self.assertNotIn("measurement", card)
        view = card["interpretation"]["measurement_context"]
        self.assertEqual(view["numeric_measurement"]["unit"], "fraction_difference")
        compact = _compact_posthoc_context(assembled)
        self.assertEqual(compact["signal_results"][0]["interpretation"]["measurement_context"], view)
        checked = _measurement_reasoning_issues((("uncertainties[0]", "Gross margin change was -10.0%."),),
                                                _context_signal_results(assembled))
        self.assertEqual(checked[0].paths, ("uncertainties[0]",))
        self.assertEqual(_context_signal_results(compact)[0]["measurement"], result.measurement.to_dict())

    def test_mixed_failure_keeps_mechanical_units_before_local_llm_price_repair(self):
        _, _, result = financial_product()
        packet = context(result)
        packet["prediction_baseline"] = {"status": "available", "mean_adjusted_close": 10, "doubling_threshold": 20, "recent_close": 11}
        original = prediction(); original["key_reasons"][0] = "To 20 requires a 106% gain from baseline."
        def repair(call):
            self.assertEqual(call["payload"]["required_change_paths"], ["key_reasons[0]"])
            self.assertIn("percentage points", call["payload"]["invalid_output"]["uncertainties"][0])
            return patch(call["payload"]["output_patch_contract"], {"op": "replace", "path": "key_reasons[0]",
                         "value": "To 20 requires a 100% gain from baseline."})
        caller = PatchCaller(original, repair)
        corrected = LLMBlindPredictor(caller).predict(packet).value
        self.assertEqual(len(caller.calls), 2)
        self.assertEqual(corrected.uncertainties[1], original["uncertainties"][1])
        self.assertIn("percentage points", corrected.uncertainties[0])

    def test_llm_cannot_author_runtime_measurement(self):
        _, document, deterministic = financial_product()
        spec = SignalSpec(signal_id="extraction", version=1, category="financial", description="Literal extraction.",
            execution_type=SignalExecutionType.LLM, modality=SignalModality.NARRATIVE, skill_file="skill.md", source_types=("sec_company_facts",))
        raw = deterministic.to_dict(); raw.update(signal_id=spec.signal_id); raw.pop("execution")
        class Caller:
            def complete_json(self, **kwargs): return {"results": [{"signal_ref": spec.ref, "result": raw}]}, AgentUsage()
        returned, _ = StructuredLLMSignalRunner(Caller()).execute(spec, (document,), "Extract literal facts.", AS_OF)
        self.assertEqual(returned.value, SignalValue.UNAVAILABLE)
        self.assertIn("runtime-owned", returned.execution_error_message)
        self.assertIsNone(returned.measurement)
