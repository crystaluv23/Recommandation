"""Actual native request cost, control-flow stops and sequential replay."""
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase

import run_mining_taxonomy_consumer_stage as stage
from stock_opportunity_agent.models import ValidationError
from stock_opportunity_agent.research.evolution_transport import StructuredOutputInvalid
from stock_opportunity_agent.research.local_role_exchange import LocalRoleRequestPending
from stock_opportunity_agent.research.mining_role_model import (
    MiningAgentRoleModel, MiningRequestBudgetExhausted,
)
from stock_opportunity_agent.research.scheme_evolution import CandidateExecutionRejected, EvolutionControlFlow
from tests.test_mining_controller import _controller, _fixture_store


LIMITS = dict(max_request_tokens=32768, max_total_tokens=98304, max_calls=6)


def client(root):
    return stage.make_client(root, {"concept": "Metric"}, {"limits": stage.LIMITS})


def view():
    cases, store = _fixture_store()
    return _controller(store, cases, object(), seed="discovery")._model_view()


def submit(caller, pending, raw):
    Path(pending.pending["outbox_path"]).write_text(raw)
    caller.local_role_exchange.submit(pending.pending["request_hash"],
        agent_id="explicit-offline-budget-test-fixture")


class MiningRequestBudgetTests(TestCase):
    def pending(self, model, payload):
        with self.assertRaises(LocalRoleRequestPending) as pending:
            model.next_action(payload)
        return pending.exception

    def metadata(self, pending):
        inbox = json.loads(Path(pending.pending["inbox_path"]).read_text())
        payload = json.loads(inbox["messages"][1]["content"])
        cost = len(json.dumps(inbox["messages"], ensure_ascii=False, sort_keys=True,
            separators=(",", ":")).encode()) + inbox["max_output_tokens"]
        budget = payload["request_budget"]
        self.assertEqual(int(budget["this_request"]), cost)
        self.assertEqual(int(budget["remaining_after"]), 98304 - budget["used"] - cost)
        self.assertLessEqual(budget["next_minimum"], cost)
        return inbox, budget, cost

    def test_native_envelope_exact_cost_pending_retry_and_sequential_reconstruction(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            first = MiningAgentRoleModel(client(root), max_output_tokens=2000, **LIMITS)
            p = self.pending(first, view()); original = Path(p.pending["inbox_path"]).read_bytes()
            _, budget, cost = self.metadata(p)
            self.assertEqual(first.reserved_tokens, 0)
            self.assertEqual(budget["calls_remaining_after"], 5)
            retry = self.pending(first, view())
            self.assertEqual(retry.pending, p.pending)
            self.assertEqual(Path(p.pending["inbox_path"]).read_bytes(), original)
            action = {"action": "inspect_manifest", "rationale": ["Inspect fixture."]}
            submit(first.caller, p, json.dumps(action))
            rebuilt = MiningAgentRoleModel(client(root), max_output_tokens=2000, **LIMITS)
            self.assertEqual(rebuilt.next_action(view()), action)
            self.assertEqual(rebuilt.reserved_tokens, cost)
            second_view = {**view(), "last_action_result": {"action": "inspect_manifest"}}
            second = self.pending(rebuilt, second_view)
            _, b2, _ = self.metadata(second)
            self.assertEqual(b2["used"], cost)
            self.assertEqual(b2["calls_used"], 1)
            rebuilt_again = MiningAgentRoleModel(client(root), max_output_tokens=2000, **LIMITS)
            rebuilt_again.next_action(view())
            same_second = self.pending(rebuilt_again, second_view)
            self.assertEqual(same_second.pending, second.pending)
            self.assertEqual(len(list((root/'exchange/inbox').glob('*.json'))), 2)
            self.assertEqual(len(list((root/'exchange/receipts').glob('*.json'))), 1)

    def test_request_stop_propagates_without_model_correction_or_research_verdict(self):
        self.assertTrue(issubclass(MiningRequestBudgetExhausted, EvolutionControlFlow))
        self.assertFalse(issubclass(MiningRequestBudgetExhausted, ValidationError))
        with TemporaryDirectory() as directory:
            root = Path(directory)
            model = MiningAgentRoleModel(client(root), max_total_tokens=1)
            cases, store = _fixture_store()
            controller = _controller(store, cases, model, seed="discovery")
            with self.assertRaises(MiningRequestBudgetExhausted):
                controller.run()
            self.assertEqual(controller._corrections, 0)
            self.assertFalse(controller.ledger.entries)
            self.assertFalse(list((root/'requests').glob('*.json')))
            self.assertFalse(list((root/'exchange/inbox').glob('*.json')))

    def test_malformed_answer_consumes_reservation_but_predispatch_guard_does_not(self):
        with TemporaryDirectory() as directory:
            root = Path(directory); caller = client(root)
            model = MiningAgentRoleModel(caller, max_output_tokens=2000, **LIMITS)
            p = self.pending(model, view()); _, _, cost = self.metadata(p)
            submit(caller, p, 'not JSON')
            with self.assertRaises(StructuredOutputInvalid):
                model.next_action(view())
            self.assertEqual(model.reserved_tokens, cost)
            self.assertEqual(model.usage.tokens, cost)
            # A new role instance reconstructs the same first request. The
            # correction guard rejects a repeated hash before any raw receive.
            fresh = MiningAgentRoleModel(caller, max_output_tokens=2000, **LIMITS)
            with caller.correction_chain(stage='mining_controller_step'):
                with self.assertRaises(StructuredOutputInvalid):
                    fresh.next_action(view())
                unconsumed = MiningAgentRoleModel(caller, max_output_tokens=2000, **LIMITS)
                with self.assertRaises(CandidateExecutionRejected):
                    unconsumed.next_action(view())
                self.assertEqual(unconsumed.reserved_tokens, 0)
                self.assertEqual(unconsumed.reserved_calls, 0)

    def test_typed_patch_keeps_grammar_and_costs_complete_correction(self):
        with TemporaryDirectory() as directory:
            root = Path(directory); model = MiningAgentRoleModel(client(root), max_output_tokens=2000, **LIMITS)
            invalid = {"invalid_output": {"action": "inspect_manifest"},
                "output_patch_contract": {"base_hash": "fixture-base"}}
            p = self.pending(model, {**view(), "last_invalid_action": invalid})
            inbox, _, _ = self.metadata(p)
            prompt = inbox['messages'][0]['content']
            self.assertIn('exactly base_hash and operations', prompt)
            self.assertNotIn('Return exactly one JSON object with keys action', prompt)
            payload = json.loads(inbox['messages'][1]['content'])
            self.assertEqual(payload['last_invalid_action'], invalid)

    def test_call_limit_stops_before_new_request_and_optional_limits_are_not_invented(self):
        with TemporaryDirectory() as directory:
            root = Path(directory); caller = client(root)
            model = MiningAgentRoleModel(caller, max_calls=1)
            p = self.pending(model, view())
            inbox = json.loads(Path(p.pending['inbox_path']).read_text())
            budget = json.loads(inbox['messages'][1]['content'])['request_budget']
            self.assertNotIn('total_limit', budget)
            self.assertNotIn('remaining_after', budget)
            submit(caller, p, '{"action":"inspect_manifest","rationale":["Inspect."]}')
            model.next_action(view())
            with self.assertRaises(MiningRequestBudgetExhausted):
                model.next_action(view())
            self.assertEqual(len(list((root/'requests').glob('*.json'))), 1)
