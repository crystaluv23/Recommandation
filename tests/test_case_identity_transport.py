"""Blind case egress, reversible evidence, and exact wire/cache boundaries."""

import json
import tempfile
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import patch
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from unittest import TestCase

from tests.test_same_request_guard import _client
from stock_opportunity_agent.models import ValidationError
from stock_opportunity_agent.research.evolution_transport import (
    ExternalRequestPending,
    _CaseIdentityProjection,
)


ALIASES = ("cik_0000895728:20250930", "Enbridge Inc / ENBRIDGE INC", "ENB")
SOURCE = ('Enbridge Inc. reports Enbridge growth. enb:RevenueMember '
          'enb:EnbridgePipelinesIncMember 000089572825000011 '
          '0000895728 {"cik":895728,"val":2446400000} enb-20250630')


class CaseIdentityTransportTests(TestCase):
    def test_explicit_short_identity_fields_do_not_use_prose_exception(self):
        aliases = ("Acme Bank", "MS", "AI", "Z")
        original = {
            "target_subject": {"company_id": "MS", "known_aliases": list(aliases)},
            "ticker": "AI", "symbol": "Z", "peer": {"symbol": "OTHER"},
            "text": "AI demand and Gen Z matter; fiscal Q2 is unchanged.",
        }
        projection = _CaseIdentityProjection(aliases, "cik_0000000001", "MS")
        view, inverse = projection.project(original)
        for item in view["target_subject"]["known_aliases"]:
            self.assertTrue(item.startswith("[ANON_ID_"))
        for item in (view["target_subject"]["company_id"], view["ticker"], view["symbol"]):
            self.assertTrue(item.startswith("[ANON_ID_"))
        self.assertEqual(view["text"], original["text"])
        self.assertEqual(view["peer"], original["peer"])
        self.assertEqual(projection.restore(view, inverse), original)

    def test_short_alias_inventory_wire_estimate_cache_and_restore_agree(self):
        aliases = ("Acme Bank", "MS")
        payload = {"target_subject": {"known_aliases": list(aliases)}, "cash": 1203,
                   "signals": [], "source_projection": [], "as_of": "2025-07-31T00:00:00+00:00"}
        with tempfile.TemporaryDirectory() as directory:
            client = _client(Path(directory))
            with client.anonymous_case(aliases=aliases, company_id="cik_0000000001", ticker="MS"):
                kwargs = dict(stage="llm_signal_batch_execute", system_prompt="Return supplied fields.",
                              payload=payload, allow_outcomes=False, max_output_tokens=4000)
                estimate = client.estimate_json_request_tokens(
                    **{key: value for key, value in kwargs.items() if key != "stage"})
                with self.assertRaises(ExternalRequestPending) as pending:
                    client.complete_json(**kwargs)
                recorded = json.loads(Path(pending.exception.request_path).read_text())
                request = recorded["request"]
                self.assertEqual(estimate, request["wire_request"]["body_bytes"] + request["max_output_tokens"])
                anonymous = json.loads(request["messages"][-1]["content"])
                self.assertTrue(all(item.startswith("[ANON_ID_") for item in
                                    anonymous["target_subject"]["known_aliases"]))
                client.cache.store(recorded["request_hash"], {"json_output": anonymous,
                                   "model": "deepseek-v4-flash", "usage": {"tokens": 10, "cost": 0}})
                self.assertEqual(client.complete_json(**kwargs)[0], payload)

    def test_unscoped_guard_inventory_projects_sec_handles_at_common_boundary(self):
        handle = "secfacts:0001309402:0001309402-22-000072:" + "a" * 64
        aliases = ("cik_0001309402",)
        payload = {"feedback_units": [{"result": {"document_fingerprint": handle}}],
                   "cash": 1309402, "snapshot_hash": "b" * 64}
        with tempfile.TemporaryDirectory() as directory:
            client = _client(Path(directory))
            kwargs = dict(stage="guarded_extension_role", system_prompt="Return supplied handle.",
                          payload=payload, allow_outcomes=True, anonymous_aliases=aliases,
                          max_output_tokens=5000)
            estimate = client.estimate_json_request_tokens(
                **{key: value for key, value in kwargs.items() if key != "stage"})
            with self.assertRaises(ExternalRequestPending) as pending:
                client.complete_json(**kwargs)
            request = json.loads(Path(pending.exception.request_path).read_text())
            recorded = request["request"]
            self.assertNotIn("0001309402", recorded["wire_request"]["body_utf8"])
            self.assertEqual(estimate, recorded["wire_request"]["body_bytes"] + recorded["max_output_tokens"])
            anonymous = json.loads(recorded["messages"][-1]["content"])
            self.assertEqual(anonymous["cash"], 1309402)
            self.assertEqual(anonymous["snapshot_hash"], "b" * 64)
            client.cache.store(request["request_hash"], {
                "json_output": anonymous, "model": "deepseek-v4-flash",
                "usage": {"tokens": 10, "cost": 0},
            })
            self.assertEqual(client.complete_json(**kwargs)[0], payload)
            self.assertIsNone(getattr(client._chain_state, "identity_projection", None))

    def test_active_case_scope_takes_precedence_over_aggregate_guard(self):
        with tempfile.TemporaryDirectory() as directory:
            client = _client(Path(directory))
            with client.anonymous_case(aliases=ALIASES, company_id="cik_0000895728", ticker="ENB"):
                projection = client._request_identity_projection(("other issuer",))
                self.assertIs(projection, client._chain_state.identity_projection)
                view, _ = projection.project(SOURCE)
                self.assertNotIn("0000895728", view)

    def test_real_terminal_needs_cannot_request_post_cutoff_actuals(self):
        from stock_opportunity_agent.research.evolution_research_validation import _future_source_date_refs

        cutoff = datetime(2025, 9, 30, tzinfo=timezone.utc).date()
        for question in (
            "What were Kinross's actual Q3 2025 production and cost of sales results?",
            "Did Kinross announce any new developments between 2025-09-30 and the end of the six-month horizon?",
        ):
            self.assertTrue(_future_source_date_refs(question, cutoff, field_name="next_information_needs"))
        self.assertFalse(_future_source_date_refs(
            "What Q3 2025 production guidance had management disclosed by 2025-09-30?",
            cutoff, field_name="next_information_needs"))
    def test_negated_future_results_scope_does_not_reject_pit_event_question(self):
        from stock_opportunity_agent.research.evolution_research_validation import _future_source_date_refs

        cutoff = datetime(2025, 9, 30, tzinfo=timezone.utc).date()
        exclusion = ", without requiring contents or results published after the prediction time?"
        actual = ("What did the target issuer disclose by the prediction time about its scheduled "
                  "third-quarter results event and any preliminary commentary on expected drivers")
        self.assertEqual(_future_source_date_refs(actual + exclusion, cutoff,
                         field_name="next_information_needs"), [])
        for main in ("What were the Q4 2025 actual results", "What results were published after the prediction time",
                     "What actual revenue occurred between September 2025 and the end of the six-month horizon"):
            self.assertTrue(_future_source_date_refs(main + exclusion, cutoff,
                            field_name="next_information_needs"))
        self.assertTrue(_future_source_date_refs(
            actual + exclusion[:-1] + " but provide the next quarter actual results?", cutoff,
            field_name="next_information_needs"))

    def test_predictor_estimator_shares_actual_prompt_payload_and_output_headroom(self):
        from stock_opportunity_agent.research.evolution_plan_roles import LLMBlindPredictor
        from stock_opportunity_agent.research.evolution_output_validation import _INCREMENTAL_ROLE_INSTRUCTION
        from unittest.mock import Mock

        caller = Mock(registration=None)
        caller.estimate_json_request_tokens.return_value = 88_449
        predictor = LLMBlindPredictor(caller)
        context = {"source": "complete already disclosed source", "state": {"decision": "finalize"}}
        self.assertEqual(predictor.estimate_prediction_tokens(context), 88_449)
        with patch("stock_opportunity_agent.research.evolution_plan_roles._complete_parsed_role",
                   return_value=(None, None)) as complete:
            predictor.predict(context)
        estimated = caller.estimate_json_request_tokens.call_args.kwargs
        sent = complete.call_args.kwargs
        self.assertEqual(estimated["system_prompt"], sent["system_prompt"] + _INCREMENTAL_ROLE_INSTRUCTION)
        for field in ("payload", "allow_outcomes", "anonymous_aliases", "max_output_tokens"):
            self.assertEqual(estimated[field], sent[field])

    def test_predictor_estimate_equals_prepared_wire_with_incremental_instructions(self):
        from stock_opportunity_agent.research.evolution_plan_roles import LLMBlindPredictor

        with tempfile.TemporaryDirectory() as directory:
            client = _client(Path(directory))
            predictor = LLMBlindPredictor(client)
            context = {"source": SOURCE}
            with client.anonymous_case(aliases=ALIASES, company_id="cik_0000895728", ticker="ENB"):
                required = predictor.estimate_prediction_tokens(context)
                predictor.set_request_token_budget(required)
                with self.assertRaises(ExternalRequestPending) as pending:
                    predictor.predict(context)
            recorded = json.loads(Path(pending.exception.request_path).read_text())["request"]
            self.assertEqual(required, recorded["wire_request"]["body_bytes"] + recorded["max_output_tokens"])
            self.assertNotIn("Enbridge", recorded["wire_request"]["body_utf8"])

    def test_generic_business_words_survive_derived_brand_masking(self):
        projection = _CaseIdentityProjection(("Energy Recovery Inc.", "ERII"), "cik_0001421517", "ERII")
        view, _ = projection.project("Energy Recovery Inc. improves energy efficiency in green travel.")
        self.assertNotIn("Energy Recovery", view)
        self.assertIn("energy efficiency in green travel", view)
        for name, ticker, member in (("Green Plains Inc.", "GPRE", "gpre:GreenPlainsRevenueMember"),
                                     ("CIENA CORP", "CIEN", "ciena:CienaProductsMember")):
            projection = _CaseIdentityProjection((name, ticker), "issuer", ticker)
            view, inverse = projection.project(member)
            self.assertNotIn(member.split(":")[1][:-6], view)
            self.assertNotIn(member.split(":")[0] + ":", view)
            self.assertEqual(projection.restore(view, inverse), member)

    def test_projection_preserves_snapshot_patch_authority_and_untouched_siblings(self):
        from stock_opportunity_agent.research.evolution_state_patch import apply_state_patch, state_patch_contract

        base = {"needs": ["Enbridge revenue", "Enbridge capacity"], "keep": "ENB source"}
        contract = state_patch_contract(base, mode="correction", obligations=[{
            "issue_code": "test_need", "must_change_paths": ["needs[0]"],
            "permitted_dependency_paths": [], "allowed_repairs": ["replace"],
        }])
        projection = _CaseIdentityProjection(ALIASES, "cik_0000895728", "ENB")
        view, inverse = projection.project({"base": base, "contract": contract,
                                           "residual": "Enbridge segment revenue"})
        response = {"base_hash": view["contract"]["base_hash"], "operations": [
            {"op": "replace", "path": "needs[0]", "value": view["residual"]}]}
        result = apply_state_patch(base, projection.restore(response, inverse), contract=contract)
        self.assertEqual(result, {"needs": ["Enbridge segment revenue", "Enbridge capacity"],
                                  "keep": "ENB source"})
        response["operations"][0]["path"] = "needs[1]"
        with self.assertRaises(ValidationError):
            apply_state_patch(base, projection.restore(response, inverse), contract=contract)

    def test_projection_roundtrip_preserves_financial_numbers_and_literal_case(self):
        projection = _CaseIdentityProjection(ALIASES, "cik_0000895728", "ENB")
        original = {"quote": SOURCE, "cik": 895728, "cash": 895728,
                    "nested": {"Enbridge document": "ENBRIDGE INC."},
                    "projection_id": "projection_hash", "content_hash": "a" * 64}
        view, inverse = projection.project(original)
        encoded = json.dumps(view)
        for identity in ("Enbridge", "ENBRIDGE", "enb:", "enb-", "0000895728"):
            self.assertNotIn(identity, encoded)
        self.assertNotEqual(view["cik"], 895728)
        self.assertEqual(view["cash"], 895728)
        self.assertEqual(view["projection_id"], original["projection_id"])
        self.assertEqual(view["content_hash"], original["content_hash"])
        self.assertEqual(projection.restore(view, inverse), original)
        with self.assertRaisesRegex(ValidationError, "undisclosed"):
            projection.restore("[ANON_ID_9999]", inverse)

    def test_persisted_actual_wire_is_blind_and_cached_quote_restores_exactly(self):
        with tempfile.TemporaryDirectory() as directory:
            client = _client(Path(directory))
            payload = {"initial_research_skill": "Inspect Enbridge.",
                       "basic_info": {"quote": SOURCE, "projection_id": "projection_hash"}}
            with client.anonymous_case(aliases=ALIASES, company_id="cik_0000895728", ticker="ENB"):
                kwargs = dict(stage="research_controller_initialize", system_prompt="Return JSON.",
                              payload=payload, allow_outcomes=False, max_output_tokens=8000)
                estimate = client.estimate_json_request_tokens(
                    **{k: v for k, v in kwargs.items() if k != "stage"})
                with self.assertRaises(ExternalRequestPending) as pending:
                    client.complete_json(**kwargs)
                request = json.loads(Path(pending.exception.request_path).read_text())
                recorded = request["request"]
                for identity in ("Enbridge", "0000895728", "enb:", 'cik\\":895728'):
                    self.assertNotIn(identity, recorded["wire_request"]["body_utf8"])
                model_input = json.loads(recorded["messages"][-1]["content"])
                self.assertGreater(estimate, len(recorded["messages"][-1]["content"]))
                client.cache.store(request["request_hash"], {
                    "json_output": {"quote": model_input["basic_info"]["quote"]},
                    "model": "deepseek-v4-flash", "usage": {"tokens": 10, "cost": 0},
                })
                output, usage = client.complete_json(**kwargs)
                self.assertEqual(output["quote"], SOURCE)
                self.assertEqual(usage.tokens, 0)
                self.assertNotIn("Enbridge", json.dumps(client.cache.load(request["request_hash"])))
            self.assertIsNone(getattr(client._chain_state, "identity_projection", None))
            self.assertEqual(payload["basic_info"]["quote"], SOURCE)

    def test_case_scope_unwinds_and_is_not_shared_between_workers(self):
        with tempfile.TemporaryDirectory() as directory:
            client = _client(Path(directory))
            with self.assertRaises(RuntimeError):
                with client.anonymous_case(aliases=ALIASES, company_id="cik_0000895728", ticker="ENB"):
                    with ThreadPoolExecutor(max_workers=1) as workers:
                        isolated = workers.submit(
                            lambda: getattr(client._chain_state, "identity_projection", None)).result()
                    self.assertIsNone(isolated)
                    raise RuntimeError("cancel")
            self.assertIsNone(getattr(client._chain_state, "identity_projection", None))

    def test_already_disclosed_tail_survives_predictor_assembly(self):
        from stock_opportunity_agent.research.evolution_core import _basic_info_projection_cards

        projections = [{"projection_id": f"projection_{i}", "exact_text": "prefix " * 400 + f"TAIL_{i}"}
                       for i in range(8)]
        cards, counts = _basic_info_projection_cards({"requests": [
            {"request": {"request_id": "operating"}, "projections": projections}]})
        self.assertEqual([row["exact_text"] for row in cards],
                         [row["exact_text"] for row in projections])
        self.assertTrue(all(not row["truncated"] for row in cards))
        self.assertEqual(counts["deferred_projections"], 0)

    def test_runtime_scopes_every_distinct_caller_and_unwinds_cancellation(self):
        from stock_opportunity_agent.data.raw_info import RawInfoStore
        from stock_opportunity_agent.research.evolution_core import (
            EvolutionCase, GroundTruth, default_information_plan,
        )
        from stock_opportunity_agent.research.plan_evolution import RuntimePlanEvaluator
        from stock_opportunity_agent.signal_library import SignalRegistry
        from tests.scheme_evolution_test_support import SEED_CATALOG

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            first, second = _client(root / "one"), _client(root / "two")
            case = EvolutionCase(
                company_id="cik_0000895728", case_id="cik_0000895728:20250930",
                prediction_time=datetime(2025, 9, 30, tzinfo=timezone.utc),
                basic_info={"company_name": "Enbridge Inc.", "ticker": "ENB"},
                ground_truth=GroundTruth(1.1),
            )
            evaluator = RuntimePlanEvaluator(
                raw_info_store=RawInfoStore(documents=()),
                controller=SimpleNamespace(caller=first), signal_agent=SimpleNamespace(caller=second),
                predictor=SimpleNamespace(caller=first), llm_signal_runner=SimpleNamespace(caller=second),
                prediction_root=root / "predictions",
            )
            def cancelled(**kwargs):
                for client in (first, second):
                    self.assertIsNotNone(client._chain_state.identity_projection)
                self.assertIs(kwargs["company_basic_source"], case.basic_info)
                raise KeyboardInterrupt()
            with patch("stock_opportunity_agent.research.plan_evolution.execute_information_plan",
                       side_effect=cancelled):
                registry = SignalRegistry(root / "signals")
                registry.install_catalog(SEED_CATALOG)
                with self.assertRaises(KeyboardInterrupt):
                    evaluator.evaluate(default_information_plan(), (case,), registry.freeze())
            for client in (first, second):
                self.assertIsNone(client._chain_state.identity_projection)

    def test_standalone_slow_runner_uses_bound_owner_for_actual_request(self):
        from stock_opportunity_agent.data.raw_info import RawInfoDocument
        from stock_opportunity_agent.research.evolution_signal_roles import StructuredLLMSignalRunner
        from stock_opportunity_agent.signal_library import LLMSignalBatchInput, SignalSpec, SignalExecutionType

        with tempfile.TemporaryDirectory() as directory:
            client = _client(Path(directory))
            runner = StructuredLLMSignalRunner(client)
            runner.set_identity_cases((SimpleNamespace(
                company_id="cik_0000895728", case_id="cik_0000895728:20250930",
                basic_info={"company_name": "Enbridge Inc.", "ticker": "ENB"}),))
            as_of = datetime(2025, 9, 30, tzinfo=timezone.utc)
            spec = SignalSpec(signal_id="guidance_review", version=1, category="catalysts",
                              description="Inspect disclosed guidance.", execution_type=SignalExecutionType.LLM,
                              source_types=("filing",), skill_file="guidance.md")
            document = RawInfoDocument.create(document_id="source", company_id="cik_0000895728",
                                               source_type="filing", published_at=as_of,
                                               available_at=as_of, content=SOURCE)
            with self.assertRaises(ExternalRequestPending) as pending:
                runner.execute_many((LLMSignalBatchInput(spec, (document,), "Inspect the literal."),), as_of)
            request = json.loads(Path(pending.exception.request_path).read_text())["request"]
            self.assertEqual(request["stage"], "llm_signal_batch_execute")
            self.assertNotIn("Enbridge", request["wire_request"]["body_utf8"])
            self.assertNotIn("0000895728", request["wire_request"]["body_utf8"])
            payload = json.loads(request["messages"][-1]["content"])
            self.assertTrue(payload["target_subject"]["known_aliases"])
            self.assertTrue(payload["target_subject"]["source_scope_is_not_event_subject"])
            self.assertIn("underwriter", request["messages"][0]["content"])
            self.assertIsNone(client._chain_state.identity_projection)
