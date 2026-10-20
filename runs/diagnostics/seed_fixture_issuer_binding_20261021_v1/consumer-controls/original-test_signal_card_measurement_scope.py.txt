"""Measurement disclosure wiring; offline replies do not prove model behavior."""

from copy import deepcopy
from dataclasses import replace
from datetime import datetime, timezone
import json
from pathlib import Path
from types import SimpleNamespace
import tempfile
from unittest import TestCase
from unittest.mock import patch

from stock_opportunity_agent.artifacts import canonical_json_hash
from stock_opportunity_agent.research.evolution_plan_roles import LLMSignalRetrievalAgent
from stock_opportunity_agent.research.evolution_core import (
    AgentStep, EvolutionControlFlow, ResearchState, default_information_plan,
    execute_information_plan,
)
from stock_opportunity_agent.data.raw_info import RawInfoStore
from stock_opportunity_agent.llm.agent import AgentUsage
from stock_opportunity_agent.signal_library import (
    FrozenSignalRegistry, SignalCoverage, SignalExecutionType, SignalExecutor,
    SignalRegistry, SignalRetrievalPolicy, SignalSpec, SignalValue,
)
from tests.evolution_runtime_test_support import ScriptedRoleCaller
from tests.test_signal_financials import _document, _row


ROOT = Path(__file__).resolve().parents[1]
AS_OF = datetime(2025, 2, 1, tzinfo=timezone.utc)
NEED = "Which original inputs should be inspected next?"


def net_spec(version=3):
    """Read the existing exact version, including its unresolved prose discrepancy."""
    path = ROOT / ("runs/cold_start/minimal_rounds_v182_integrated/signals/financial/"
                   f"net_share_retirement_yoy/versions/v{version}/spec.json")
    return SignalSpec.from_dict(json.loads(path.read_text()))


def snapshot(specs):
    return FrozenSignalRegistry(version=1,
        registry_hash=canonical_json_hash([spec.to_dict() for spec in specs]),
        specs=tuple(specs), skills={})


class SignalCardMeasurementScopeTests(TestCase):
    def setUp(self):
        network = patch("socket.socket", side_effect=AssertionError("network forbidden"))
        network.start()
        self.addCleanup(network.stop)

    def _wire(self, frozen):
        caller = ScriptedRoleCaller([{"selections": []}])
        agent = LLMSignalRetrievalAgent(caller)
        agent.set_evaluation_context(AS_OF)
        agent.select((NEED,), frozen, {})
        self.assertEqual(caller.stages, ["signal_retrieval_cards"])
        return caller.calls[0]["payload"]

    def _core_wire(self, specs, functions=None):
        """Use the real core/executor injection; stop after the real selector parser."""
        class RoutingBoundary(EvolutionControlFlow):
            pass
        class Selector(LLMSignalRetrievalAgent):
            def select(self, *args, **kwargs):
                super().select(*args, **kwargs)
                raise RoutingBoundary()
        def forbidden(*args, **kwargs):
            raise AssertionError("post-routing execution is outside this wiring fixture")
        frozen = snapshot(specs)
        caller = ScriptedRoleCaller([{"selections": []}])
        executor = SignalExecutor(frozen, RawInfoStore(), deterministic_functions=functions)
        controller = SimpleNamespace(initialize=lambda *args: AgentStep(
            ResearchState(next_information_needs=(NEED,)), AgentUsage()), reflect=forbidden)
        with self.assertRaises(RoutingBoundary):
            execute_information_plan(plan=default_information_plan(), company_id="issuer_1",
                company_basic_source={}, prediction_time=AS_OF, signal_registry=frozen,
                signal_executor=executor, controller=controller, signal_agent=Selector(caller),
                predictor=SimpleNamespace(predict=forbidden, reflect=forbidden),
                prediction_sink=forbidden, ground_truth_provider=forbidden)
        self.assertEqual(caller.stages, ["signal_retrieval_cards"])
        return caller.calls[0]["payload"]

    def _execute_facts(self, spec, *, weighted_prior=100, weighted_current=110,
                       include_weighted=True, prior_unit="shares"):
        facts = {"CommonStockSharesOutstanding": {"units": {"shares": [
            _row(None, "2023-12-31", 200, "2024-02-01"),
            _row(None, "2024-12-31", 50, "2025-01-20"),
        ]}}}
        if include_weighted:
            units = {"shares": [_row("2024-01-01", "2024-12-31", weighted_current, "2025-01-20")]}
            units.setdefault(prior_unit, []).append(
                _row("2023-01-01", "2023-12-31", weighted_prior, "2024-02-01"))
            facts["WeightedAverageNumberOfSharesOutstandingBasic"] = {"units": units}
        content = json.dumps({"facts": {"us-gaap": facts}}, sort_keys=True, separators=(",", ":"))
        return SignalExecutor(snapshot((spec,)), RawInfoStore(documents=(
            _document("scope-facts", content, source_type=spec.source_types[0]),
        ))).execute_batch((spec.ref,), company_id="issuer_1", as_of=AS_OF).results[0]

    def test_actual_selector_wire_preserves_complete_eligible_scopes_and_versions(self):
        commentary = SignalSpec(signal_id="commentary_scope_fixture", version=1,
            category="management", description="Compare original operating statements.",
            execution_type=SignalExecutionType.LLM, skill_file="offline-skill.md",
            source_types=("filing", "news"), retrieval_policy=SignalRetrievalPolicy(
                query_terms=("original operations",), lookback_days=365,
                comparison_requirement="Compare contemporaneous statements in the same unit.",
                required_source_groups=(("filing",), ("news",)),
                minimum_distinct_periods=2, minimum_period_span_days=90,
                minimum_observations=3))
        market = SignalSpec(signal_id="market_scope_fixture", version=1, category="market",
            description="Measure original price observations.",
            execution_type=SignalExecutionType.DETERMINISTIC,
            function="market.price_momentum_126d", source_types=("prices",),
            retrieval_policy=SignalRetrievalPolicy(query_terms=("daily prices",),
                minimum_observations=127))
        for version in (2, 3):
            with self.subTest(version=version):
                specs = (net_spec(version), commentary, market)
                frozen = snapshot(specs)
                before = deepcopy([spec.to_dict() for spec in frozen.specs])
                before_hashes = frozen.registry_hash, frozen.learning_hash
                payload = self._wire(frozen)
                cards = {card["signal_ref"]: card for card in payload["available_signal_cards"]}
                self.assertEqual(set(cards), {spec.ref for spec in specs})
                for spec in specs:
                    scope = cards[spec.ref]["measurement_scope"]
                    self.assertEqual(scope["signal_ref"], spec.ref)
                    self.assertEqual(scope["source_types"], list(spec.source_types))
                    self.assertEqual(scope["raw_retrieval"], spec.retrieval_policy.to_dict())
                    if spec.execution_type is SignalExecutionType.DETERMINISTIC:
                        self.assertEqual(scope["execution"]["callable_status"], "unknown")
                        self.assertIsNone(scope["execution"]["contract"])
                    else:
                        self.assertEqual(scope["execution"], {"type": "llm"})
                cards[commentary.ref]["measurement_scope"]["raw_retrieval"]["required_source_groups"][0].append("mutated")
                cards[market.ref]["measurement_scope"]["source_types"].append("mutated")
                self.assertEqual([spec.to_dict() for spec in frozen.specs], before)
                self.assertEqual((frozen.registry_hash, frozen.learning_hash), before_hashes)

    def test_actual_core_uses_override_contract_and_only_declared_configured_parameters(self):
        from stock_opportunity_agent.signal_library import signal_parameter_names

        @signal_parameter_names("positive_min")
        def override(*args):
            """Offline override contract: positive_min is the sole configured consumer."""
            raise AssertionError("routing must not execute the measurement")
        spec = replace(net_spec(), parameters={"positive_min": 0.02, "negative_max": -0.05,
            "fixtures": ["DO_NOT_DISCLOSE_FIXTURE"], "unused": {"nested": [1]}})
        before = spec.to_dict()
        payload = self._core_wire((spec,), {spec.function: override})
        scope = payload["available_signal_cards"][0]["measurement_scope"]
        execution = scope["execution"]
        self.assertEqual(execution["callable_status"], "registered")
        self.assertEqual(execution["contract"], override.__doc__)
        self.assertEqual(execution["parameter_names"], ["positive_min"])
        self.assertEqual(execution["configured_parameters"], {"positive_min": 0.02})
        self.assertNotIn("DO_NOT_DISCLOSE_FIXTURE", json.dumps(payload))
        execution["configured_parameters"]["positive_min"] = 99
        execution["parameter_names"].append("mutated")
        self.assertEqual(spec.to_dict(), before)

    def test_actual_core_undocumented_or_missing_callable_does_not_claim_builtin(self):
        def undocumented(*args):
            raise AssertionError("routing must not execute the measurement")
        original = net_spec()
        missing = replace(original, signal_id="missing_scope_fixture", function="custom.unregistered")
        payload = self._core_wire((original, missing), {original.function: undocumented})
        executions = {card["signal_ref"]: card["measurement_scope"]["execution"]
                      for card in payload["available_signal_cards"]}
        self.assertEqual(set(executions), {original.ref, missing.ref})
        for ref, status in ((original.ref, "registered"), (missing.ref, "missing")):
            self.assertEqual(executions[ref]["callable_status"], status)
            self.assertIsNone(executions[ref]["contract"])
            self.assertIsNone(executions[ref]["parameter_names"])
            self.assertIsNone(executions[ref]["configured_parameters"])

    def test_registry_cards_and_real_selector_share_the_same_scope_projection(self):
        with tempfile.TemporaryDirectory() as directory:
            registry = SignalRegistry(Path(directory) / "signals")
            registry.install_catalog(ROOT / "configs/signals_v1.json")
            frozen = registry.freeze()
            standalone = self._wire(frozen)
            library = {card.ref: card.to_dict() for card in registry.list_signal_cards()}
            for card in standalone["available_signal_cards"]:
                self.assertEqual(card["measurement_scope"], library[card["signal_ref"]]["measurement_scope"])
            executor = SignalExecutor(frozen, RawInfoStore())
            injected = self._core_wire(frozen.specs)
            library = {card.ref: card.to_dict() for card in registry.list_signal_cards(
                deterministic_functions=executor.deterministic_functions)}
            for card in injected["available_signal_cards"]:
                self.assertEqual(card["measurement_scope"], library[card["signal_ref"]]["measurement_scope"])

    def test_weighted_average_basis_ending_and_unit_counterexamples_preserve_v3_definition(self):
        spec = net_spec()
        before = spec.to_dict()
        result = self._execute_facts(spec)
        self.assertEqual(result.value, SignalValue.NEGATIVE)
        self.assertEqual(result.interpretation, "net_share_retirement_yoy=-0.1")
        self.assertTrue(all('"start"' in evidence.exact_span
                            for evidence in result.supporting_evidence))
        for arguments in ({"include_weighted": False}, {"prior_unit": "thousands_of_shares"}):
            with self.subTest(arguments=arguments):
                self.assertEqual(self._execute_facts(spec, **arguments).value, SignalValue.UNAVAILABLE)
        implausible = self._execute_facts(spec, weighted_prior=0.1)
        self.assertEqual(implausible.value, SignalValue.NEGATIVE)
        self.assertEqual(implausible.coverage, SignalCoverage.PARTIAL)
        self.assertEqual(implausible.confidence, 0.5)
        self.assertIn("implausible_value", implausible.interpretation)
        self.assertIn("an implausible prior-year denominator yields unavailable", spec.retrieval_policy.comparison_requirement)
        execution = self._core_wire((spec,))["available_signal_cards"][0]["measurement_scope"]["execution"]
        self.assertIn("not an unavailable guard", execution["contract"])
        self.assertEqual(spec.to_dict(), before)

    def test_cash_ratio_documented_default_matches_native_numeric_behavior(self):
        spec = SignalSpec(signal_id="cash_ratio_scope_fixture", version=1, category="financial",
            description="Measure original same-period cash and current liabilities.",
            execution_type=SignalExecutionType.DETERMINISTIC,
            function="financial.cash_to_current_liabilities_ratio", source_types=("financials",))
        facts = {"facts": {"us-gaap": {
            "CashAndCashEquivalentsAtCarryingValue": {"units": {"USD": [
                _row(None, "2024-12-31", 100, "2025-01-20")]}},
            "LiabilitiesCurrent": {"units": {"USD": [
                _row(None, "2024-12-31", 200, "2025-01-20")]}},
        }}}
        document = _document("cash-ratio", json.dumps(facts, sort_keys=True,
            separators=(",", ":")), source_type="financials")
        for parameters, expected in (({}, SignalValue.POSITIVE), ({"positive_min": 1}, SignalValue.NEGATIVE)):
            configured = replace(spec, parameters=parameters)
            result = SignalExecutor(snapshot((configured,)), RawInfoStore(documents=(document,))).execute_batch(
                (configured.ref,), company_id="issuer_1", as_of=AS_OF).results[0]
            self.assertEqual(result.value, expected)
            self.assertEqual(result.interpretation, "cash_to_current_liabilities_ratio=0.5")
            execution = self._core_wire((configured,))["available_signal_cards"][0]["measurement_scope"]["execution"]
            self.assertIn("positive_min (default 0)", " ".join(execution["contract"].split()))
            self.assertEqual(execution["configured_parameters"], parameters)
