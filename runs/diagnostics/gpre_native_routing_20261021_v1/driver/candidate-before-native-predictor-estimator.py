#!/usr/bin/env python3
"""Read accepted GPRE H_init, then bound genuine native routing before execution.

No source/initial role is repeated. Nonempty selection returns to core and stops
at its actual executor entry before preparation/calculation; empty stops earlier.
"""
from __future__ import annotations

import argparse
from dataclasses import asdict, replace
from datetime import datetime
import json
from pathlib import Path
from types import SimpleNamespace
import traceback

import run_gpre_native_initial_stage as initial
from diagnose_executed_answer_scope import StageContract, binding, read_json
from stock_opportunity_agent.artifacts import atomic_write_json, canonical_json_hash
from stock_opportunity_agent.data.reviewed_snapshot import open_raw_info_store
from stock_opportunity_agent.llm import get_model
from stock_opportunity_agent.llm.agent import AgentUsage
from stock_opportunity_agent.models import ValidationError
from stock_opportunity_agent.research.evolution_core import (
    AgentStep, EvolutionControlFlow, InformationPlan, ResearchState,
    RuntimeBudgetExceeded, RuntimeLimits, _consume_model_step,
    execute_information_plan, project_basic_info_bundle,
)
from stock_opportunity_agent.research.evolution_plan_roles import LLMResearchController, LLMSignalRetrievalAgent
from stock_opportunity_agent.research.evolution_transport import ExternalAttemptLedger, StructuredRoleClient
from stock_opportunity_agent.research.local_role_exchange import LocalRoleExchange, LocalRoleRequestPending
from stock_opportunity_agent.signal_library import SignalExecutor, SignalRegistry

REPO = initial.REPO
ROOT = REPO / 'runs/diagnostics/gpre_native_routing_20261021_v1/stage'
SPEC = REPO / 'spec/scripts/run_gpre_native_routing_stage.md'
PARENT = initial.ROOT
PARENT_REVIEW = PARENT.parent / 'independent-preflight/actual-initial-review.json'
PARENT_COMPLETION_SHA = '58082055515d8809e51a0ba897378cc9fb39c4fc61c426867c514c44c0ab5ec0'
PARENT_REVIEW_SHA = '455ca111aedd1f8e107de32b023f51ebb4003e3650bdd3ad980f8b15005090d2'
PRIOR_TOKENS = 61888
LIMITS = dict(initial.LIMITS)
ALLOWED_STAGES = {'signal_retrieval_cards', 'signal_retrieval_cards_correction',
                  'signal_retrieval_cards_patch_mechanics_correction'}


class RoutingBoundary(EvolutionControlFlow):
    """The actual native select AgentStep has been persisted; no tail may run."""


def forbidden(*args, **kwargs):
    raise ValidationError('routing diagnostic cannot initialize a model or enter the execution tail')


def parent_stage_files():
    """Bind all parent artifacts except its one non-authoritative dispatch lock."""
    operational_lock = str((PARENT / 'exchange/.dispatch.lock').resolve())
    return [row for row in initial.files(PARENT) if row['path'] != operational_lock]


def authorities():
    """Consume exact accepted parent bytes read-only, never resume the parent."""
    parent_inputs, parent_contract = initial.verify()
    completion = read_json(PARENT / 'completion.json')
    binding(PARENT / 'completion.json', PARENT_COMPLETION_SHA)
    binding(PARENT_REVIEW, PARENT_REVIEW_SHA)
    accepted = read_json(PARENT / 'samples/h01/initial_state.json')
    parsed = read_json(PARENT / 'samples/h01/parsed_step.json')
    if ({k: accepted[k] for k in ('state', 'usage', 'metadata', 'request_hashes')} != parsed
            or accepted['usage'] != accepted['native_budget_usage']
            or accepted['usage']['tokens'] != PRIOR_TOKENS
            or accepted['usage']['llm_calls'] != 1
            or completion['logical_reservation'] != PRIOR_TOKENS
            or completion['status'] != 'accepted_initial_requires_independent_review'):
        raise ValidationError('accepted initial state or its actual budget lineage differs')
    binding(Path(completion['initial_state']['path']), completion['initial_state']['sha256'])
    parent_manifest = read_json(PARENT / 'manifest.json')
    originals = initial.unique([*parent_stage_files(), binding(PARENT_REVIEW),
        *parent_manifest['source_files'], parent_manifest['expectations']])
    inputs = {'sample': parent_inputs['sample'], 'sources': parent_inputs['sources'],
              'plan': parent_inputs['plan'], 'registry_group': parent_inputs['registry_group'],
              'accepted_initial_step': accepted,
              'bootstrap': read_json(PARENT / 'samples/h01/bootstrap.json'),
              'parent_completion': binding(PARENT / 'completion.json'),
              'parent_independent_review': binding(PARENT_REVIEW)}
    return inputs, originals, parent_contract


def prepare(*, expectations):
    """Freeze the fixed child with the genuine parent and an opaque private oracle."""
    if ROOT.exists():
        raise ValidationError('routing destination must be new')
    with initial.guards():
        inputs, originals, parent_contract = authorities()
    runtime = replace(RuntimeLimits(**parent_contract['runtime_limits']), max_llm_calls=5)
    contract = {'schema_version': 'gpre-native-routing-v1', 'backend': 'independent-subagent',
                'limits': LIMITS, 'runtime_limits': asdict(runtime),
                'prior_case_usage': inputs['accepted_initial_step']['native_budget_usage'],
                'remaining_case_logical_units': 256000 - PRIOR_TOKENS,
                'native_selection_budget': 256000 - PRIOR_TOKENS - runtime.finalization_token_reserve,
                'scope': 'native routing to executor entry only; no calculation or prepared inputs',
                'neutral_path_exact_handoff_required': True}
    code = initial.unique([*initial.code_bindings(), binding(Path(__file__)), binding(SPEC)])
    initial.check(originals + code)
    manifest = {'root': str(ROOT), 'source_files': originals, 'code_files': code,
                'inputs_hash': canonical_json_hash(inputs), 'contract_hash': canonical_json_hash(contract),
                'expectations': binding(Path(expectations))}
    manifest['manifest_hash'] = canonical_json_hash(manifest)
    ROOT.mkdir(parents=True, exist_ok=False)
    for name, value in (('inputs', inputs), ('contract', contract), ('manifest', manifest)):
        atomic_write_json(ROOT / (name + '.json'), value)
    return {'manifest_hash': manifest['manifest_hash'], 'source_bindings': len(originals),
            'code_bindings': len(code), 'prior_case_logical_usage': PRIOR_TOKENS, 'new_authors': 0}


def verify():
    manifest = read_json(ROOT / 'manifest.json')
    digest = manifest.pop('manifest_hash')
    inputs, contract = read_json(ROOT / 'inputs.json'), read_json(ROOT / 'contract.json')
    if (manifest['root'] != str(ROOT) or canonical_json_hash(manifest) != digest
            or canonical_json_hash(inputs) != manifest['inputs_hash']
            or canonical_json_hash(contract) != manifest['contract_hash']
            or contract['limits'] != LIMITS or contract['prior_case_usage']['tokens'] != PRIOR_TOKENS):
        raise ValidationError('routing frozen stage changed or relocated')
    initial.check(manifest['source_files'] + manifest['code_files'] + [manifest['expectations']])
    return inputs, contract


class Budget:
    """Count new physical handoffs separately from prior-inclusive case reservations."""
    def __init__(self):
        self.requests = []
        self.total = PRIOR_TOKENS

    def __call__(self, event):
        if event.get('event_type') != 'request_ready':
            return
        request = read_json(Path(event['request_path']))['request']
        if request['stage'] not in ALLOWED_STAGES:
            forbidden()
        reservation = len(json.dumps(request['messages'], ensure_ascii=False, sort_keys=True,
                                     separators=(',', ':')).encode('utf-8')) + request['max_output_tokens']
        if (reservation > LIMITS['max_request_tokens'] or self.total + reservation > LIMITS['max_case_tokens']
                or len(self.requests) >= LIMITS['max_local_role_calls']):
            raise RuntimeBudgetExceeded('routing request/case/two-new-author ceiling')
        self.total += reservation
        self.requests.append({'request_hash': event['request_hash'], 'reservation': reservation})
        atomic_write_json(ROOT / 'request-reservations.json', {'prior_case_usage': PRIOR_TOKENS,
                          'requests': self.requests, 'combined_case_reservation': self.total})


def run_native(inputs, contract, snapshot, client):
    """Let core rebuild bootstrap and routing arguments, retaining no invented state."""
    sample = inputs['sample']
    source = inputs['sources'][sample['source']]
    resolver = initial.orientation._ObservedResolver(
        open_raw_info_store(source['root'], reviewed_snapshot=source).snapshot())
    plan = InformationPlan.from_dict(inputs['plan'])
    accepted = inputs['accepted_initial_step']
    prior_usage = AgentUsage(**accepted['usage'])
    limits = RuntimeLimits(**contract['runtime_limits'])

    class Controller(LLMResearchController):
        def initialize(self, actual_plan, basic_info):
            model, lineage = project_basic_info_bundle(resolver.observed_bundle)
            actual = {'plan': actual_plan.to_dict(), 'bundle': resolver.observed_bundle.to_dict(),
                      'model_context': basic_info, 'projection_lineage': lineage,
                      'evaluation_context': self.evaluation_context, 'evaluation_anchor': self.evaluation_anchor,
                      'computed_metrics': self.computed_metrics,
                      'document_channel_set_by_core': self.document_channel is not None}
            if model != basic_info or canonical_json_hash(actual) != canonical_json_hash(inputs['bootstrap']):
                raise ValidationError('recomputed native bootstrap differs from accepted initial authority')
            initial.orientation._save_exact(ROOT / 'recomputed-bootstrap.json', actual)
            return AgentStep(ResearchState.from_dict(accepted['state']), prior_usage, accepted['metadata'])

        def reflect(self, *args, **kwargs):
            return forbidden(*args, **kwargs)

    class Selector(LLMSignalRetrievalAgent):
        def select(self, information_needs, registry, prior_fingerprints, prior_results=None, **kwargs):
            context = {'information_needs': list(information_needs),
                       'eligible_signal_refs': list(kwargs['eligible_signal_refs']),
                       'research_state': kwargs['research_state'].to_dict(),
                       'prior_fingerprints': dict(prior_fingerprints), 'prior_results': dict(prior_results or {}),
                       'prior_context_tags': list(kwargs['prior_context_tags']),
                       'evaluation_context': self.evaluation_context,
                       'native_request_token_budget': self.request_token_budget,
                       'deterministic_callable_refs': sorted(self.deterministic_functions or {}),
                       'post_select_core_caps': {'max_signals_per_round': limits.max_signals_per_round,
                           'max_llm_signals_per_round': limits.max_llm_signals_per_round,
                           'remaining_signal_calls': limits.max_signal_calls}}
            if self.request_token_budget != contract['native_selection_budget']:
                raise ValidationError('core remaining routing budget differs')
            initial.orientation._save_exact(ROOT / 'native-select-context.json', context)
            step = super().select(information_needs, registry, prior_fingerprints, prior_results, **kwargs)
            combined = _consume_model_step(prior_usage, step.usage, limits)
            initial.orientation._save_exact(ROOT / 'accepted-selection.json', {
                'selections': [s.to_dict() for s in step.value], 'metadata': dict(step.metadata),
                'new_selection_usage': asdict(step.usage), 'native_combined_case_usage': asdict(combined),
                'request_hashes': list(client.request_hash_trace),
                'scope': 'accepted selector intentions; separate first-entry record shows core truncation',
                'original_need_count': len(information_needs),
                'original_needs_retained': list(information_needs),
                'post_select_core_caps': context['post_select_core_caps']})
            if not step.value:
                atomic_write_json(ROOT / 'routing-boundary.json', {
                    'kind': 'native_empty_selection_before_core_finalization', 'executor_entry_attempts': 0})
                raise RoutingBoundary()
            return step

    class Executor(SignalExecutor):
        def execute_batch(self, refs, **kwargs):
            # This replaces no production computation: boundary before super or
            # prepare_inputs. Base-class execution remains guarded as forbidden.
            selected = read_json(ROOT / 'accepted-selection.json')
            intents = {row['signal_ref']: row for row in selected['selections']}
            exact_refs = list(refs)
            atomic_write_json(ROOT / 'routing-boundary.json', {
                'kind': 'native_core_first_executor_entry_before_preparation',
                'executor_entry_attempts': 1, 'actual_first_batch_refs': exact_refs,
                'actual_first_batch_intents': [intents[ref] for ref in exact_refs],
                'company_id': kwargs['company_id'], 'as_of': kwargs['as_of'].isoformat(),
                'prior_fingerprints': kwargs.get('prior_fingerprints', {}),
                'Signal_calculations': 0, 'prepare_inputs': 0})
            raise RoutingBoundary()

    identity = sample['identity']
    with client.anonymous_case(aliases=tuple(identity['identity_aliases']),
                               company_id=sample['company_id'], ticker=identity['ticker']):
        execute_information_plan(plan=plan, company_id=sample['company_id'], company_basic_source=identity,
            prediction_time=datetime.fromisoformat(sample['prediction_time']), signal_registry=snapshot,
            signal_executor=Executor(snapshot, raw_info_store=resolver.store, resolver=resolver),
            controller=Controller(client), signal_agent=Selector(client),
            predictor=SimpleNamespace(predict=forbidden, reflect=forbidden),
            prediction_sink=forbidden, ground_truth_provider=forbidden, limits=limits)
    raise ValidationError('native execution returned without routing boundary')


def resume():
    """Reach pending or accepted selection; never execute a selected Signal."""
    inputs, contract = verify()
    if any((ROOT / name).exists() for name in ('failure.json', 'completion.json')):
        raise ValidationError('terminal routing stage cannot reenter')
    budget = Budget()
    try:
        with initial.guards():
            candidate_root = ROOT / 'unused_candidates'
            candidate_root.mkdir(exist_ok=True)
            group = inputs['registry_group']
            before = initial.files(group['root'])
            registry = SignalRegistry(group['root'], candidate_root=candidate_root)
            snapshot = registry.snapshot_from_refs(group['version'], tuple(group['refs']))
            if snapshot.registry_hash != group['registry_hash'] or before != initial.files(group['root']):
                raise ValidationError('exact readonly Registry identity drift')
            client = StructuredRoleClient(registration=get_model('independent-subagent'),
                contract=StageContract(contract), workspace=ROOT,
                ledger=ExternalAttemptLedger(ROOT / 'unused_external_attempts.json', max_attempts=1, max_total_cost=.01),
                local_role_exchange=LocalRoleExchange(ROOT / 'exchange', max_calls=2),
                allow_external=False, environ={}, on_progress=budget)
            run_native(inputs, contract, snapshot, client)
    except LocalRoleRequestPending as pending:
        verify()
        return {'status': 'pending', **pending.pending, 'combined_case_reservation': budget.total,
                'prior_case_usage': PRIOR_TOKENS, 'new_request_count': len(budget.requests)}
    except RoutingBoundary:
        verify()
        result = {'status': 'accepted_routing_intents_require_independent_review',
                  'accepted_selection': binding(ROOT / 'accepted-selection.json'),
                  'combined_case_reservation': budget.total, 'new_requests': budget.requests,
                  'prior_case_usage': PRIOR_TOKENS, 'Signal_execution': 0, 'Reflect': 0, 'Predictor': 0,
                  'source_queries': 0, 'labels': 0, 'model_API': 0,
                  'boundary': binding(ROOT / 'routing-boundary.json')}
        atomic_write_json(ROOT / 'completion.json', result)
        return result
    except BaseException as exc:
        atomic_write_json(ROOT / 'failure.json', {'error_type': type(exc).__name__, 'error': str(exc),
                                                'traceback': traceback.format_exc()})
        raise


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    action = parser.add_mutually_exclusive_group(required=True)
    action.add_argument('--prepare', action='store_true')
    action.add_argument('--resume', action='store_true')
    action.add_argument('--submit')
    parser.add_argument('--expectations', type=Path)
    parser.add_argument('--agent-id')
    args = parser.parse_args()
    if args.prepare:
        if args.expectations is None:
            parser.error('--prepare requires --expectations')
        result = prepare(expectations=args.expectations)
    elif args.resume:
        result = resume()
    else:
        verify()
        if any((ROOT / name).exists() for name in ('failure.json', 'completion.json')):
            raise ValidationError('terminal routing stage cannot submit')
        result = LocalRoleExchange(ROOT / 'exchange', max_calls=2).submit(args.submit, agent_id=args.agent_id or '')
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))


if __name__ == '__main__':
    main()
