"""Local/permission Jev conflicts fail before remote provider construction."""
from pathlib import Path
from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import patch
import json
import tempfile

from tests.evolution_runtime_test_support import make_contract
from stock_opportunity_agent.llm import get_model
from stock_opportunity_agent.research.evolution_control import (
    EvolutionRunContract, build_run_contract, _validate_cycle_execution_request, _parallel_decision_roles,
)
from stock_opportunity_agent.research.evolution_transport import ExternalExecutionNotReady
from stock_opportunity_agent.research.evolution_plan_roles import LLMSignalRetrievalAgent, LLMBlindPredictor


class LocalFactoryRouteGuardTests(TestCase):
    @patch("stock_opportunity_agent.research.evolution_control.current_code_revision", return_value="unit-fixture-revision")
    def test_judge_conflict_rejects_and_other_local_roles_preserve_hybrid(self, _revision):
        base = make_contract()
        for local_role in ('judge','proposer','mining','update'):
            aliases = {role: 'independent-subagent' if role==local_role else 'deepseek-v4-flash'
                       for role in ('judge','proposer','mining','update')}
            with self.subTest(role=local_role), tempfile.TemporaryDirectory() as directory:
                manifest = Path(directory)/'dataset.json'
                manifest.write_text(json.dumps({'approval_status':'human_approved','locked_test_sealed':True}))
                from contextlib import nullcontext
                expected = self.assertRaises(ExternalExecutionNotReady) if local_role=="judge" else nullcontext()
                with expected:
                    build_run_contract(run_id='local-guard',dataset_manifest_path=manifest,inventory=None,
                        raw_info_oracle=SimpleNamespace(oracle_id='test'),raw_info_inventory_hash='a'*64,
                        initial_signal_registry_version=1,initial_signal_registry_hash='b'*64,priors={},
                        role_aliases=aliases,project_root=Path(__file__).resolve().parents[1],
                        limits=base.limits,max_external_attempts=10,max_total_cost=1,
                        parallel_jev_decisions=True,environ={})
                data = base.to_dict()
                data['parallel_jev_decisions'] = True
                data['models'][local_role] = get_model('independent-subagent').to_public_dict()
                data['models']['jev'] = {'alias':'openrouter-jev','provider':'openrouter','model':'remote'}
                expected = self.assertRaises(ExternalExecutionNotReady) if local_role=="judge" else nullcontext()
                with expected:
                    EvolutionRunContract.from_dict(data)

    def test_preflight_and_runtime_reject_before_provider(self):
        contract = make_contract()
        object.__setattr__(contract,'parallel_jev_decisions',True)
        object.__setattr__(contract,'models',{'judge':get_model('independent-subagent').to_public_dict()})
        with self.assertRaises(ExternalExecutionNotReady):
            _validate_cycle_execution_request(contract,allow_data_external=False)
        callers = (SimpleNamespace(registration=get_model('independent-subagent')),
                   SimpleNamespace(local_role_exchange=object()),
                   SimpleNamespace(contract=contract),
                   SimpleNamespace(registration=get_model('deepseek-v4-flash'),allow_external=False))
        for caller in callers:
            with self.subTest(caller=caller), patch('stock_opportunity_agent.research.evolution_control.OpenRouterJevClient.from_environ',side_effect=AssertionError('provider constructed')):
                with self.assertRaises(ExternalExecutionNotReady):
                    _parallel_decision_roles(caller,parallel_jev_decisions=True,environ={})

    def test_disabled_jev_keeps_native_roles(self):
        caller = SimpleNamespace(registration=get_model('independent-subagent'),allow_external=False)
        with patch('stock_opportunity_agent.research.evolution_control.OpenRouterJevClient.from_environ',side_effect=AssertionError('provider constructed')):
            router,predictor = _parallel_decision_roles(caller,parallel_jev_decisions=False,environ={})
        self.assertIsInstance(router,LLMSignalRetrievalAgent)
        self.assertIsInstance(predictor,LLMBlindPredictor)
