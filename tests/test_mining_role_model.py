import unittest

from tests.evolution_runtime_test_support import (  # noqa: F403
    AgentUsage,
    ScriptedRoleCaller,
)

from stock_opportunity_agent.models import ValidationError
from stock_opportunity_agent.research.mining_role_model import (
    MINING_CONTROLLER_STAGE,
    MiningAgentRoleModel,
)


class MiningRoleModelTests(unittest.TestCase):
    def test_adapter_passes_view_and_returns_parsed_action(self) -> None:
        action = {
            "action": "inspect_manifest",
            "rationale": ["Check measurable families first."],
        }
        caller = ScriptedRoleCaller([action])
        model = MiningAgentRoleModel(caller)

        result = model.next_action(
            {"state": "ready", "label_map": {"case-001": "positive"}}
        )

        self.assertEqual(result, action)
        self.assertEqual(caller.stages, [MINING_CONTROLLER_STAGE])
        call = caller.calls[0]
        self.assertIn("label_map", call["payload"])
        self.assertTrue(call["allow_outcomes"])
        self.assertIn("record_no_pattern", call["system_prompt"])
        self.assertEqual(model.usage.llm_calls, 1)

    def test_adapter_accumulates_usage_and_rejects_non_object(self) -> None:
        caller = ScriptedRoleCaller(
            [
                {"action": "inspect_catalog", "rationale": ["x"]},
                ["not", "an", "object"],
            ]
        )
        model = MiningAgentRoleModel(caller)

        model.next_action({"state": "ready"})
        with self.assertRaises(ValidationError):
            model.next_action({"state": "exploring"})

        self.assertEqual(model.usage.llm_calls, 2)


if __name__ == "__main__":
    unittest.main()
