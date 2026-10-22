"""Native-path/control-plane tests in temporary roots; no production author or dispatch."""
from dataclasses import asdict
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import patch

from scripts import run_icfr_native_capability_stage as stage
from stock_opportunity_agent.artifacts import canonical_json_hash as digest
from stock_opportunity_agent.data.raw_info import RawInfoStore
from stock_opportunity_agent.models import ValidationError
from stock_opportunity_agent.research.evolution_core import AgentUsage, ResearchState
from stock_opportunity_agent.research.evolution_transport import StructuredOutputInvalid
from stock_opportunity_agent.research.local_role_exchange import LocalRoleExchange, LocalRoleRequestPending
from stock_opportunity_agent.research.mining_role_model import MiningAgentRoleModel
from stock_opportunity_agent.research.mining_controller import LabelAwareMiningController
from stock_opportunity_agent.research.signal_evolution import SignalEvolutionEngine


class ICFRNativeCapabilityStageTests(TestCase):
    def client(self, root, *, input_only=False):
        stage.save(root / 'contract.json', {'limits': stage.LIMITS})
        budget = stage.Budget(root, input_only=input_only)
        return stage.make_client(root, budget), budget

    def kwargs(self, payload=None):
        view = LabelAwareMiningController(store=RawInfoStore(), model=SimpleNamespace(), case_pairs=(),
            measurable_evidence_manifest={}, signal_catalog=(), seed='discovery', label_map={})._model_view()
        view.update(payload or {'synthetic': True})
        return {'stage': 'mining_controller_step', 'system_prompt': 'Synthetic test role.',
                'payload': view, 'allow_outcomes': True,
                'max_output_tokens': 100}

    def answer(self, root, pending, text='{}'):
        Path(pending['outbox_path']).write_text(text)
        return LocalRoleExchange(root / 'exchange', max_calls=728).submit(
            pending['request_hash'], agent_id='/root/synthetic_test_actor')

    def test_unique_answer_budget_and_pending_replay(self):
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            client, budget = self.client(root)
            for _ in range(2):
                with self.assertRaises(LocalRoleRequestPending) as caught:
                    client.complete_json(**self.kwargs())
                if _ == 0:
                    first = caught.exception.pending
                self.assertEqual(first, caught.exception.pending)
                self.assertEqual(budget.used(), (0, 0))
            self.answer(root, first)
            value, usage = client.complete_json(**self.kwargs())
            self.assertEqual(value, {})
            self.assertEqual(budget.used(), (1, usage.tokens))
            client.complete_json(**self.kwargs())
            self.assertEqual(budget.used(), (1, usage.tokens))

    def test_malformed_submitted_answer_consumes_unique_allowance(self):
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            client, budget = self.client(root)
            with self.assertRaises(LocalRoleRequestPending) as caught:
                client.complete_json(**self.kwargs())
            self.answer(root, caught.exception.pending, '{')
            for _ in range(2):
                with self.assertRaises(StructuredOutputInvalid):
                    client.complete_json(**self.kwargs())
                self.assertEqual(budget.used()[0], 1)

    def test_one_current_pending_and_budget_stop_are_control_flow(self):
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            client, budget = self.client(root)
            with self.assertRaises(LocalRoleRequestPending):
                client.complete_json(**self.kwargs())
            with self.assertRaises(stage.StageBudgetStop):
                client.complete_json(**self.kwargs({'another': 'new request'}))
            self.assertEqual(len(list((root / 'exchange/inbox').glob('*.json'))), 1)
            self.assertEqual(budget.used(), (0, 0))
            self.assertTrue(issubclass(stage.StageBudgetStop, stage.EvolutionControlFlow))

    def test_single_ceiling_blocks_before_receive_without_charging(self):
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            client, budget = self.client(root)
            with self.assertRaises(stage.StageBudgetStop):
                client.complete_json(**self.kwargs({'text': 'x' * 262144}))
            self.assertEqual(budget.used(), (0, 0))
            self.assertFalse(list((root / 'exchange/inbox').glob('*.json')))

    def test_per_scope_ceiling_does_not_reset_at_cache_reconstruction(self):
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            client, budget = self.client(root)
            with self.assertRaises(LocalRoleRequestPending) as caught:
                client.complete_json(**self.kwargs())
            self.answer(root, caught.exception.pending)
            client.complete_json(**self.kwargs())
            with patch.dict(stage.SCOPE_LIMITS, {'mining': (1, 12 * stage.MIB)}):
                # Exact answered replay is legal at the ceiling; a new answer is not.
                client.complete_json(**self.kwargs())
                with self.assertRaises(stage.StageBudgetStop):
                    client.complete_json(**self.kwargs({'different': 1}))
            self.assertEqual(budget.used()[0], 1)

    def test_one_answer_can_have_two_candidate_scopes_without_global_double_charge(self):
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            client, budget = self.client(root)
            budget.scope = 'candidate:first'
            with self.assertRaises(LocalRoleRequestPending) as caught:
                client.complete_json(**self.kwargs())
            self.answer(root, caught.exception.pending)
            client.complete_json(**self.kwargs())
            budget.scope = 'candidate:second'
            client.complete_json(**self.kwargs())
            self.assertEqual(budget.used()[0], 1)
            self.assertEqual(budget.used('candidate:first')[0], 1)
            self.assertEqual(budget.used('candidate:second')[0], 1)

    def test_phase_allowance_stays_frozen_when_later_receipts_arrive(self):
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            client, budget = self.client(root)
            budget.scope = 'fast:case-001'
            initial = budget.phase_allowance('case-001-route')
            with self.assertRaises(LocalRoleRequestPending) as caught:
                client.complete_json(**self.kwargs())
            self.answer(root, caught.exception.pending)
            self.assertLess(budget.remaining(), initial)
            self.assertEqual(budget.phase_allowance('case-001-route'), initial)

    def test_native_shared_model_budget_prefix_replays_after_completed_seed(self):
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            client, budget = self.client(root)
            engine = object.__new__(stage.Engine)
            engine.stage_root = root
            engine.workspace = SimpleNamespace(experiments_root=root / 'experiments')
            def controller(model, seed):
                return engine._new_mining_controller(cycle_id=1, store=RawInfoStore(), model=model,
                    case_pairs=(), measurable_evidence_manifest={}, signal_catalog=(), seed=seed,
                    label_map={}, backlog_needs=())
            model = MiningAgentRoleModel(client, max_request_tokens=262144)
            with self.assertRaises(LocalRoleRequestPending) as caught:
                controller(model, 'hypothesis').run()
            self.answer(root, caught.exception.pending,
                json.dumps({'action': 'record_deferred', 'rationale': ['Synthetic test termination.']}))
            model = MiningAgentRoleModel(client, max_request_tokens=262144)
            controller(model, 'hypothesis').run()
            self.assertEqual(model.reserved_calls, 1)
            with self.assertRaises(LocalRoleRequestPending) as caught:
                controller(model, 'discovery').run()
            first = caught.exception.pending
            first_payload = json.loads(stage.read(first['inbox_path'])['messages'][1]['content'])
            self.assertEqual(first_payload['request_budget']['call_limit'], 80)
            self.assertEqual(first_payload['request_budget']['total_limit'], 12 * stage.MIB)
            self.assertEqual(first_payload['request_budget']['calls_used'], 1)
            # Reconstruct with final receipt state; completed hypothesis is not called again.
            model = MiningAgentRoleModel(client, max_request_tokens=262144)
            with patch.object(client, 'complete_json', wraps=client.complete_json) as calls:
                controller(model, 'hypothesis').run()
                self.assertEqual(calls.call_count, 0)
                with self.assertRaises(LocalRoleRequestPending) as caught:
                    controller(model, 'discovery').run()
            self.assertEqual(caught.exception.pending, first)
            self.assertEqual(budget.used()[0], 1)

    def test_independent_semantic_receipt_binds_oracle_targets_and_all_items(self):
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            stage.save(root / 'manifest.json', {'frozen': True})
            stage.save(root / 'private-oracle.json', {'private': True})
            targets = {'items': {'candidate:v1': {'hash': 'synthetic'}}}
            fields = ('faithful_definition', 'faithful_orientation')
            self.assertIsNone(stage._review(root, 'semantic-review', targets, fields))
            receipt = {'schema_version': 'icfr-native-independent-review-v1', 'reviewer_id': '/root/reviewer',
                'manifest_hash': digest(stage.read(root / 'manifest.json')),
                'targets_sha256': stage.binding(root / 'semantic-review-targets.json')['sha256'],
                'oracle_sha256': stage.binding(root / 'private-oracle.json')['sha256'],
                'items': {'candidate:v1': {'accepted': True, 'limitations': [],
                    'faithful_definition': True, 'faithful_orientation': False}}}
            stage.atomic_write_json(root / 'semantic-review.json', receipt)
            with self.assertRaises(ValidationError):
                stage._review(root, 'semantic-review', targets, fields)
            receipt['items']['candidate:v1']['accepted'] = False
            stage.atomic_write_json(root / 'semantic-review.json', receipt)
            self.assertFalse(stage._review(root, 'semantic-review', targets, fields)['items']['candidate:v1']['accepted'])
            (root / 'private-oracle.json').write_text('{}')
            with self.assertRaises(ValidationError):
                stage._review(root, 'semantic-review', targets, fields)

    def test_no_author_pending_and_input_only_on_actual_approved_native_axis(self):
        # Only temporary stage setup; no fixed stage exists or receives an answer.
        with TemporaryDirectory() as temporary:
            root = Path(temporary) / 'stage'
            with patch.object(stage, 'STAGE_ROOT', root):
                stage.prepare(root)
                self.assertEqual(stage.read(root / 'workspace/state.json')['last_completed_round'], 0)
                self.assertIsNone(stage.read(root / 'workspace/cycle_state.json')['active_cycle'])
                self.assertFalse(list((root / 'workspace/experiments').rglob('slow_loop_validation.json')))
                with self.assertRaises(ValidationError):
                    stage.prepare(root)
                before = stage.advance(root, input_only=True)
                self.assertEqual(before['status'], 'input_only_no_dispatch', before)
                self.assertFalse(list((root / 'exchange/inbox').glob('*.json')))
                result = stage.advance(root)
                self.assertEqual(result['status'], 'pending_independent_role', result)
                pending = result['pending']
                payload = json.loads(stage.read(pending['inbox_path'])['messages'][1]['content'])
                self.assertEqual(payload['request_budget']['call_limit'], 80)
                self.assertEqual(payload['request_budget']['total_limit'], 12 * stage.MIB)
                self.assertEqual(payload['backlog_disclosure']['total_backlog_count'], 265)
                self.assertEqual(len(payload['meta_memory_disclosures']), 6)
                self.assertEqual(len(stage.read(root / 'private-oracle.json')['source_documents']), 263)
                self.assertEqual(len(stage.read(root / 'inputs/baseline.json')['refs']), 18)
                self.assertNotIn('actual_management_icfr_conclusion', json.dumps(payload))
                # Receipt count/final budget state is not inserted into early role payloads.
                self.assertEqual(stage.advance(root)['pending'], pending)
                self.assertEqual(stage.Budget(root).used(), (0, 0))
                with self.assertRaises(ValidationError):
                    stage.submit(root, '0' * 64, '/root/not_current')
                # Deterministic input drift is rejected before native construction.
                (root / 'inputs/factory.json').write_text('{}')
                with self.assertRaises(ValidationError):
                    stage.advance(root)

    def test_terminal_reentry_and_scoped_reopen(self):
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            with patch.object(stage, 'STAGE_ROOT', root), patch.object(stage, 'verify', return_value={}):
                stage.save(root / 'an-output.json', {'native': True})
                expected = {'status': 'completed_acceptance_failed'}
                stage._seal(root, expected)
                self.assertEqual(stage.inspect(root), expected)
                with self.assertRaises(ValidationError):
                    stage.advance(root)
                (root / 'an-output.json').write_text('{}')
                with self.assertRaises(ValidationError):
                    stage.inspect(root)

    def test_guards_forbid_business_and_labels_but_allow_memory_sources(self):
        with stage.guards():
            self.assertEqual(len(RawInfoStore().documents), 0)
            with self.assertRaises(stage.StageBudgetStop):
                stage.LabelStore('not-used')
            with self.assertRaises(stage.StageBudgetStop):
                SignalEvolutionEngine.run_cycle(None, cycle_id=1)
            with self.assertRaises(stage.StageBudgetStop):
                stage.socket.create_connection(('example.com', 443))

    def test_native_technical_admission_publication_and_four_fast_artifact_chains(self):
        """Synthetic deterministic wiring control, not an ICFR semantic capability result."""
        from dataclasses import replace
        from stock_opportunity_agent.research.evolution_core import ResearchDecision, AgentStep
        from stock_opportunity_agent.signal_library import SignalSpec
        from tests.scheme_evolution_test_support import (
            SEED_CATALOG, EmptyMiningModel, NoChangeUpdateModel, candidate_growth_fixture, make_case,
        )
        from datetime import datetime
        from stock_opportunity_agent.data.raw_info import RawInfoDocument
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            client, budget = self.client(root)
            registry = stage.SignalRegistry(root / 'workspace/signals', candidate_root=root / 'workspace/signals_candidates')
            registry.install_catalog(SEED_CATALOG)
            baseline = registry.freeze()
            stage.save(root / 'inputs/baseline.json', stage._snapshot_record(baseline))
            current = registry.load_spec('revenue_growth_yoy:v1')
            spec = replace(current, signal_id='synthetic_native_growth', version=1,
                description='Measure annual revenue growth under synthetic distinct threshold.',
                parameters={**current.parameters, 'positive_min': .22})
            fixture = candidate_growth_fixture()
            registry.stage_candidate(spec, skill=None, tests=(fixture,), origin='fixture:synthetic-only')
            case = make_case('synthetic-admission', 1.1)
            # Closed fixture body is reused as explicitly synthetic source, never a business source.
            documents = []
            for i, raw in enumerate(fixture['documents']):
                documents.append(RawInfoDocument.create(document_id='synthetic-' + str(i), company_id=case.company_id,
                    source_type=raw['source_type'], content=raw['content'], metadata=raw.get('metadata', {}),
                    published_at=datetime.fromisoformat(raw['available_at']),
                    available_at=datetime.fromisoformat(raw['available_at'])))
            engine = SignalEvolutionEngine(registry=registry, raw_info_store=RawInfoStore(documents=documents),
                discovery_cases=(case,), identity_cases=(case,), meta_memory=stage.PlanMetaMemory(),
                workspace=stage.EvolutionWorkspace(root / 'workspace'), mining_model=EmptyMiningModel(),
                update_model=NoChangeUpdateModel(), llm_signal_runner=None)
            engine.budget = budget
            stage.save(root / 'candidate-scopes' / (spec.ref + '.json'), {'scope': 'candidate:synthetic'})
            output = {'candidate_refs': [spec.ref], 'induction_case_ids': {spec.ref: [case.case_id]}}
            receipt = {'items': {spec.ref: {'accepted': True}}}
            with patch.object(engine.effectiveness_evaluator, 'evaluate', side_effect=AssertionError('effect forbidden')):
                publication = stage._publish(root, engine, output, receipt)
            self.assertEqual(publication['promoted'], [spec.ref])
            self.assertEqual(registry.load_research_status(spec.ref)['effect_status'], 'unverified')
            self.assertEqual(stage._transition(root, engine, stage.read(root / 'technical-decision.json')), publication)
            selection = stage.SignalSelectionDecision.legacy(spec.ref)
            final = ResearchState(next_information_needs=(stage.NEED,),
                                  decision=ResearchDecision.FINALIZE)
            reflection = AgentStep(final, metadata={'need_dispositions': {'items': []}})
            # Role outputs are explicit synthetic test doubles; executor/validators/context stay native.
            with patch.object(stage.LLMSignalRetrievalAgent, 'select', return_value=AgentStep((selection,))) as select, \
                 patch.object(stage.LLMResearchController, 'reflect', return_value=reflection) as reflect:
                for case_ref in stage.CONTROLS:
                    use = stage._fast(root, engine, client, case_ref, case)
                    self.assertEqual(use['new_exact_refs_executed'], [spec.ref])
                    self.assertFalse(use['committed_use'])
                    self.assertEqual(stage.SignalRound.from_dict(stage.read(root / 'fast' / case_ref / 'apply.json')['round']).selected_signals,
                                     (spec.ref,))
                    context = stage.read(root / 'fast' / case_ref / 'final-context.json')
                    self.assertIn(spec.ref, json.dumps(context))
                self.assertEqual(select.call_count, 4)
                self.assertEqual(reflect.call_count, 4)
            self.assertEqual(budget.used(), (0, 0))
            self.assertEqual(engine.workspace.last_completed_round, 0)
            self.assertEqual(engine.workspace.last_completed_cycle, 0)

    def test_native_materializer_keeps_handoff_and_control_flow_in_candidate_scope(self):
        """No replacement S5 implementation: the actual inherited entry gets the original seed evidence."""
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            engine = object.__new__(stage.Engine)
            engine.stage_root, engine.budget = root, stage.Budget(root)
            candidate = {'measurement': {'observable': 'synthetic'}, 'evidence_refs': ['original-ref']}
            evidence = {'original-ref': {'read_windows': [{'readable_text': 'Uncropped synthetic source.'}]}}
            with patch.object(SignalEvolutionEngine, '_materialize_controller_candidate',
                              side_effect=stage.StageBudgetStop('synthetic host stop')) as native:
                with self.assertRaises(stage.StageBudgetStop):
                    engine._materialize_controller_candidate(candidate, caller=SimpleNamespace(),
                        evidence=evidence, failures={}, seed='discovery')
                self.assertIs(native.call_args.kwargs['evidence'], evidence)
                self.assertEqual(native.call_args.kwargs['seed'], 'discovery')
                self.assertTrue(engine.budget.scope.startswith('candidate:'))
            self.assertFalse(list((root / 'materialized').glob('*.json')))

    def test_old_answer_accounting_metadata_drift_blocks_a_new_request(self):
        """Completed-seed cache skips cannot let a changed reservation lower spent budget."""
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            client, budget = self.client(root)
            with self.assertRaises(LocalRoleRequestPending) as caught:
                client.complete_json(**self.kwargs())
            pending = caught.exception.pending
            self.answer(root, pending)
            self.assertEqual(budget.used()[0], 1)
            meta_path = root / 'request-scopes' / (pending['request_hash'] + '.json')
            original = stage.read(meta_path)
            stage.atomic_write_json(meta_path, {**original, 'reservation': 1})
            with self.assertRaises(stage.StageBudgetStop):
                client.complete_json(**self.kwargs({'new': 'must not dispatch'}))
            self.assertEqual(len(list((root / 'exchange/inbox').glob('*.json'))), 1)
            stage.atomic_write_json(meta_path, original)
            request_path = Path(original['request']['path'])
            native = stage.read(request_path)
            changed = json.loads(json.dumps(native))
            changed['request']['max_output_tokens'] += 1
            stage.atomic_write_json(request_path, changed)
            with self.assertRaises(stage.StageBudgetStop):
                budget.records()

    def test_zero_explicit_native_remainder_is_not_replaced_with_single_cap(self):
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            client, budget = self.client(root)
            for remainder in (0, -1):
                with self.assertRaises(stage.StageBudgetStop):
                    client.complete_json(**{**self.kwargs(), 'max_request_tokens': remainder})
            self.assertFalse(list((root / 'transport/requests').glob('*.json')))
            self.assertEqual(budget.used(), (0, 0))

    def test_input_only_cannot_cross_an_accepted_phase_or_seal_success(self):
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            stage.save(root / 'mining-output.json', {'candidate_refs': []})
            with patch.object(stage, 'STAGE_ROOT', root), patch.object(stage, 'verify', return_value={}):
                with self.assertRaises(ValidationError):
                    stage.advance(root, input_only=True)
            self.assertFalse((root / 'completion.json').exists())

    def test_semantic_bundle_binds_original_controller_candidate_and_seed_handoff(self):
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            origin = {'seed': 'discovery', 'controller_candidate': {'measurement': 'synthetic unchanged'}}
            stage.save(root / 'candidate-scopes/synthetic:v1.json', origin)
            stage.save(root / 'seeds/discovery/terminal.json', {'evidence': {'original': True}})
            registry = SimpleNamespace(load_candidate=lambda ref: (SimpleNamespace(to_dict=lambda: {'synthetic': True}), None),
                load_candidate_tests=lambda ref: ({'synthetic': True},), candidate_hash=lambda ref: 'a' * 64)
            bundle = stage._candidate_bundle(registry, 'synthetic:v1', root=root)
            self.assertEqual(bundle['origin']['controller_candidate'], origin['controller_candidate'])
            stage._check([bundle['origin']['scope_binding'], bundle['origin']['seed_terminal_binding']])
            (root / 'seeds/discovery/terminal.json').write_text('{}')
            with self.assertRaises(ValidationError):
                stage._check([bundle['origin']['seed_terminal_binding']])

    def test_prepare_authority_checks_original_wire_and_sealed_prefix_not_current_bytes(self):
        """A shape-valid current copy cannot replace accepted wire/factory/input bytes."""
        with TemporaryDirectory() as temporary:
            base = Path(temporary)
            parent = base / 'parent'
            prefix = parent / 'workspace/experiments/cycles/cycle-0001'
            committed = base / 'input_manifest.json'
            stage.save(committed, {'synthetic': 'historically committed input'})
            stage.save(parent / 'approved_cases.json', stage.read(committed))
            stage.save(parent / 'factory-input.json', {'synthetic': 'accepted factory'})
            stage.save(prefix / 'slow_input.json', {'synthetic': 'accepted input'})
            stage.save(prefix / 'slow_memory.json', {'synthetic': 'accepted memory'})
            input_hash, memory_hash = digest(stage.read(prefix / 'slow_input.json')), digest(stage.read(prefix / 'slow_memory.json'))
            stage.save(parent / 'reflection-boundary.json', {'slow_input_hash': input_hash, 'slow_memory_hash': memory_hash})
            manifest = {'source_bindings': [stage.binding(committed)],
                        'native_prepared': {'slow_input_hash': input_hash}}
            manifest['manifest_hash'] = digest(manifest)
            stage.save(parent / 'manifest.json', manifest)
            files = {p.relative_to(parent).as_posix(): stage.binding(p)['sha256']
                     for p in parent.rglob('*') if p.is_file()}
            stage.save(parent / 'completion.json', {'files': files, 'result': {'synthetic': 'accepted prefix only'}})
            wire = base / 'first-wire.json'
            stage.save(wire, {'synthetic': 'original opaque wire'})
            obligations = {'source_authority': {'first_native_manifest_wire': stage.binding(wire)}}
            with patch.object(stage, 'PARENT', parent):
                stage._accepted_prefix_authority(obligations)
                for path in (wire, parent / 'approved_cases.json', parent / 'factory-input.json',
                             prefix / 'slow_input.json', prefix / 'slow_memory.json'):
                    original = path.read_bytes()
                    path.write_text('{"synthetic":"changed but parseable"}')
                    with self.subTest(path=path.name), self.assertRaises(ValidationError):
                        stage._accepted_prefix_authority(obligations)
                    path.write_bytes(original)
                # Neither old source runtime code nor unrelated mutable progress is consulted.
                (parent / 'progress.json').write_text('{"status":"changed"}')
                stage._accepted_prefix_authority(obligations)
