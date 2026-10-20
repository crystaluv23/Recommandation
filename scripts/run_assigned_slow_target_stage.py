"""Run only an assigned native Controller child from a sealed accepted frontier.

No source/Reflect replay, Signal execution, publication or full Slow is allowed.
The immutable parent is provenance; this child has its own contract and budget.
"""
from __future__ import annotations

import argparse
from contextlib import contextmanager
from copy import deepcopy
from datetime import datetime, timezone
import json
from pathlib import Path
import shutil
import subprocess
import sys
from unittest.mock import patch

from scripts import run_reviewed_slow_feedback_stage as base
from stock_opportunity_agent.artifacts import atomic_write_json, canonical_json_hash as digest
from stock_opportunity_agent.models import ValidationError
from stock_opportunity_agent.research.evolution_control import EvolutionRunContract
from stock_opportunity_agent.research.evolution_core import (
    _mask_identity_values, _scoped_slow_identity_guard_inventory, _evidence_source_family,
)
from stock_opportunity_agent.research.evolution_transport import StructuredRoleClient, ExternalAttemptLedger
from stock_opportunity_agent.research.local_role_exchange import LocalRoleExchange, LocalRoleRequestPending
from stock_opportunity_agent.research.mining_controller import LabelAwareMiningController
from stock_opportunity_agent.research.mining_role_model import MiningAgentRoleModel, MINING_CONTROLLER_STAGE
from stock_opportunity_agent.research.signal_evolution import SignalEvolutionEngine
from stock_opportunity_agent.research.mining_agent_tools import derive_attribute_vocabulary

REPO = Path(__file__).resolve().parents[1]
ROOT = REPO / 'runs/diagnostics/assigned_slow_target_20261021_v1/stage'
PARENT = base.STAGE_ROOT
PARENT_COMPLETION_SHA = '3640c700b68f002582be664e4e907caf33f840535e68671fcd0220c73057fe63'
TARGET = 'reflection-7d08d205fe330564'
MAX_CALLS, REQUEST_CAP, TOTAL_CAP = 3, 131072, 393216
SPEC = REPO / 'spec/scripts/run_assigned_slow_target_stage.md'
read, binding = base.read, base.binding


class FrontierCaptured(base.StageRejected):
    """Stop before cache/dispatch after the native transport made its request."""


def _root(root):
    root = Path(root).resolve()
    if root != ROOT.resolve():
        raise ValidationError('assigned Controller destination is fixed')
    return root


def _code():
    return sorted(base._code() + [binding(Path(__file__)), binding(SPEC),
        binding(REPO / 'tests/test_assigned_slow_target_stage.py')], key=lambda row: row['path'])


def _source():
    """Verify the exact sealed parent, never treating its code as current code."""
    if binding(PARENT / 'completion.json')['sha256'] != PARENT_COMPLETION_SHA:
        raise base.StageRejected('sealed parent identity changed')
    if (binding(base.CASES)['sha256'] != base.CASES_SHA
        or binding(PARENT / 'approved_cases.json')['sha256'] != base.CASES_SHA
        or binding(base.REVIEWED / 'reviewed_snapshot.json')['sha256'] != base.REVIEWED_SHA):
        raise base.StageRejected('approved cases or qualified view authority changed')
    seal = read(PARENT / 'completion.json')
    if seal['files'] != base._stage_files(PARENT):
        raise base.StageRejected('sealed parent file set or bytes changed')
    manifest, factory = read(PARENT / 'manifest.json'), read(PARENT / 'factory-input.json')
    if manifest['native_prepared']['target_need_ref'] != TARGET:
        raise base.StageRejected('parent native target identity differs')
    boundary = read(PARENT / 'controller-boundary.json')
    if TARGET not in boundary['pending_need_refs']:
        raise base.StageRejected('assigned target was already handled')
    if len(factory['backlog_needs']) != 265 or sum(row['need_ref'] == TARGET for row in factory['backlog_needs']) != 1:
        raise base.StageRejected('parent complete backlog differs')
    first = []
    for path in sorted((PARENT / 'exchange/inbox').glob('*.json')):
        for message in read(path)['messages']:
            if message['role'] == 'user':
                value = json.loads(message['content'])
                if 'need_disposition_contract' in value and 'last_invalid_action' not in value:
                    first.append((path, value))
    if len(first) != 1:
        raise base.StageRejected('first native Controller wire is ambiguous')
    return manifest, factory, first[0]


class Budget:
    """Enforce the child aggregate and per-family exact-request reservations."""
    def __init__(self, request_root=None):
        self.requests = {}
        for path in sorted(request_root.glob('*.json')) if request_root is not None else ():
            row = read(path)
            self.reserve(row['request_hash'], row['request'])

    def __call__(self, event):
        if event.get('event_type') == 'request_ready':
            row = read(event['request_path'])
            self.reserve(row['request_hash'], row['request'])

    def reserve(self, key, request):
        if key != digest(request) or request['stage'] != MINING_CONTROLLER_STAGE or request['max_output_tokens'] != 4000:
            raise base.StageRejected('only bounded Controller requests are authorized')
        payload = json.loads(next(row['content'] for row in request['messages'] if row['role'] == 'user'))
        family = 'correction' if payload.get('last_invalid_action') else 'regular'
        size = len(json.dumps(request['messages'], ensure_ascii=False, sort_keys=True, separators=(',', ':')).encode()) + 4000
        row = {'family': family, 'reservation': size}
        if key in self.requests:
            if self.requests[key] != row:
                raise base.StageRejected('request replay identity changed')
            return
        if (size > REQUEST_CAP or len(self.requests) >= MAX_CALLS
            or sum(v['reservation'] for v in self.requests.values()) + size > TOTAL_CAP
            or sum(v['family'] == family for v in self.requests.values()) >= (1 if family == 'correction' else 2)):
            raise base.StageRejected('assigned Controller budget exhausted')
        self.requests[key] = row


class Caller:
    def __init__(self, client):
        self.client = client

    def __getattr__(self, name):
        return getattr(self.client, name)

    def complete_json(self, **kwargs):
        if kwargs.get('stage') != MINING_CONTROLLER_STAGE:
            raise base.StageRejected('accepted source/Reflect prefix cannot run again')
        kwargs['system_prompt'] += (
            '\nThis independent child module assigns native backlog need_ref ' + TARGET +
            ' as the task to address. Only inspect_catalog scope=backlog and '
            'record_need_dispositions are authorized. The original controlled '
            'backlog page is already read. Retain uncertainty and other pending needs. '
            'Stop at the first accepted native need-progress write. No expected '
            'disposition or answer is supplied by this assignment.')
        return self.client.complete_json(**kwargs)


@contextmanager
def _guard(root, *, setup=False):
    def forbidden(*args, **kwargs):
        raise base.StageRejected('Controller-only child cannot repeat accepted prefix/full axis')
    with base._guard(root, protect_copies=not setup):
        with patch.object(SignalEvolutionEngine, '_prepare_slow_input', forbidden), \
             patch.object(SignalEvolutionEngine, '_prepare_slow_memory', forbidden), \
             patch.object(SignalEvolutionEngine, '_mining_context', forbidden), \
             patch.object(SignalEvolutionEngine, '_run_controller_mining_axis', forbidden):
            yield


def _contract(code):
    value = deepcopy(read(PARENT / 'run_contract.json')['contract'])
    limits = dict(value['limits'])
    limits.update(max_llm_calls=3, max_tokens=TOTAL_CAP, max_agent_steps=3,
        max_request_tokens=REQUEST_CAP, max_case_tokens=TOTAL_CAP, max_case_llm_calls=3,
        max_local_role_calls=3, max_structured_corrections=1)
    value.update(run_id=ROOT.parent.name, created_at=datetime.now(timezone.utc).isoformat(),
        limits=limits, max_external_attempts=3, max_total_cost=0.01,
        code_revision=subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=REPO, text=True).strip()
            + ':assigned-controller-' + digest(code))
    return EvolutionRunContract.from_dict(value)


def _construct(root, manifest, *, capture=False):
    """Use real constructors, accepted context and the shared native factory."""
    base._verify_contracts(root, manifest['run_contract'])
    contract = EvolutionRunContract.load_frozen(root / 'workspace/run_contract.json')
    work = root / 'workspace'
    history = base.validate_slow_history_manifest(workspace=work, contract=contract)
    discovery, identities = base._cases(read(root / 'approved_cases.json'))
    store = base.open_raw_info_store(base.REVIEWED, reviewed_snapshot=manifest['reviewed_source'])
    if len(store.documents) != 1780:
        raise base.StageRejected('qualified original document population differs')
    registry = base.SignalRegistry(work / 'signals', candidate_root=work / 'signals_candidates')
    snapshot = base._historical_registry_snapshot(registry)
    if snapshot.version != history['registry_version'] or snapshot.registry_hash != history['registry_hash']:
        raise base.StageRejected('copied stable Registry identity differs')
    workspace = base.EvolutionWorkspace(work)
    workspace.start_or_resume_cycle(run_contract_hash=contract.contract_hash, target_plan_rounds=0,
        cycle_mode='slow_only', initial_signal_registry_version=snapshot.version,
        initial_signal_registry_hash=snapshot.registry_hash, observed_signal_registry_version=snapshot.version,
        observed_signal_registry_hash=snapshot.registry_hash, max_slow_cycles=1)
    meta = base.PlanMetaMemory(entries=base._rebased_history_meta_entries(
        base.RoundMetaEntry.from_dict(row) for row in history['fast_context']['meta_entries']))
    old_first = read(Path(manifest['first_wire']['path']))
    view = json.loads(next(m['content'] for m in old_first['messages'] if m['role'] == 'user'))
    budget = Budget(root / 'transport/requests')
    def progress(event):
        if capture and event.get('event_type') == 'request_ready':
            request = read(event['request_path'])['request']
            actual = json.loads(next(m['content'] for m in request['messages'] if m['role'] == 'user'))
            base._immutable(root / 'preflight-wire.json', {'expected': manifest['first_wire'],
                'actual_user': actual, 'expected_user': view, 'equal': digest(actual) == digest(view)})
            if digest(actual) != digest(view):
                raise base.StageRejected('first native Controller wire differs from accepted frontier')
            raise FrontierCaptured('exact native wire captured before cache/dispatch')
        budget(event)
    transport_root = root / ('preflight' if capture else 'transport')
    client = StructuredRoleClient(registration=base.get_model('independent-subagent'),
        contract=EvolutionRunContract.load_frozen(root / 'workspace/run_contract.json'),
        workspace=transport_root, local_role_exchange=LocalRoleExchange(root / 'exchange', max_calls=3),
        ledger=ExternalAttemptLedger(root / 'unused_external_attempts.json', max_attempts=3, max_total_cost=0.01),
        allow_external=False, environ={}, on_progress=progress)
    caller = Caller(client)
    engine = SignalEvolutionEngine(registry=registry, raw_info_store=store, discovery_cases=discovery,
        identity_cases=identities, workspace=workspace, meta_memory=meta,
        mining_model=base.LLMSignalMiningModel(caller), update_model=base.LLMSignalUpdateModel(caller),
        llm_signal_runner=None)
    base._preserved(root, manifest)
    prefix = PARENT / 'workspace/experiments/cycles/cycle-0001'
    engine._active_slow_input = read(prefix / 'slow_input.json')
    engine._active_slow_memory = read(prefix / 'slow_memory.json')
    if digest(engine._active_slow_memory) != manifest['accepted_memory_hash']:
        raise base.StageRejected('accepted prefix memory differs')
    engine._active_sampling_manifest = engine._active_slow_input['sampling_manifest']
    engine._mining_memory_index = engine._controller_memory_index()
    factory = read(PARENT / 'factory-input.json')
    dev = engine._manifest_cases('dev_case_ids')
    pairs = [(f'case-{index:03d}', case) for index, case in enumerate(dev, 1)]
    catalog = tuple({'signal_ref': spec.ref, 'description': spec.description} for spec in snapshot.specs)
    originals = {row['signal_ref']: {'spec': engine.registry.load_spec(row['signal_ref']).to_dict(),
        'skill': engine.registry.load_skill(row['signal_ref'])} for row in catalog}
    model = MiningAgentRoleModel(Caller(client), identity_aliases=_scoped_slow_identity_guard_inventory(
        engine._discovery_cases_by_id.values()))
    documents = [doc for case in dev for doc in engine.raw_info_store.documents
        if doc.company_id == case.company_id and doc.available_at <= case.prediction_time
        and _evidence_source_family(doc.source_type) in {'filing', 'transcript', 'news'}]
    controller = engine._new_mining_controller(cycle_id=1, store=engine.raw_info_store, model=model,
        case_pairs=pairs, measurable_evidence_manifest=_mask_identity_values(
            engine._h1_measurable_evidence_manifest(pairs), engine.slow_role_identity_guards, expand_aliases=False),
        signal_catalog=catalog, signal_originals=originals, seed='hypothesis',
        backlog_needs=factory['backlog_needs'], identity_aliases=engine.slow_role_identity_guards,
        attribute_vocabulary=derive_attribute_vocabulary(documents),
        prior_modality_footprints=factory['prior_modality_footprints'],
        validation_sink=lambda _candidate: (_ for _ in ()).throw(base.StageRejected('candidate forbidden')),
        label_map=factory['label_map'], research_axis=factory['research_axis'],
        meta_memory_briefs=factory['meta_memory_briefs'], memory_index=engine._mining_memory_index,
        slow_method_memory=factory['slow_method_memory'], meta_memory_disclosures=factory['meta_memory_disclosures'])
    page = read(PARENT / 'controlled-page.json')
    controller._execute('inspect_catalog', {'action': 'inspect_catalog', 'scope': 'backlog',
        'cursor': page['cursor'], 'rationale': ['Stage-authorized controlled native page initialization.']})
    return controller


def _verify(root):
    manifest = read(root / 'manifest.json')
    if digest({k: v for k, v in manifest.items() if k != 'manifest_hash'}) != manifest['manifest_hash']:
        raise base.StageRejected('child manifest changed')
    if manifest['code'] != _code():
        raise base.StageRejected('child executable source/spec changed')
    if (manifest['profile'] != 'assigned-slow-target-v1' or manifest['target_need_ref'] != TARGET
        or manifest['max_calls'] != 3 or manifest['total_cap'] != TOTAL_CAP
        or manifest['request_cap'] != REQUEST_CAP):
        raise base.StageRejected('fixed assigned child identity/limits changed')
    _source()
    for row in manifest['source_bindings']:
        if binding(row['path']) != row:
            raise base.StageRejected('accepted source bytes changed')
    base._verify_contracts(root, manifest['run_contract'])
    for name, expected in manifest['copied_files'].items():
        if binding(root / 'workspace' / name)['sha256'] != expected:
            raise base.StageRejected('child immutable copy changed')
    base._preserved(root, manifest)
    return manifest


def prepare(root):
    """Freeze a new child and compare its exact native pre-dispatch wire."""
    root = _root(root)
    if root.exists():
        raise ValidationError('child stage exists; setup may not be repeated')
    parent, factory, first = _source()
    code = _code()
    contract = _contract(code)
    root.mkdir(parents=True)
    try:
        with _guard(root, setup=True):
            work = root / 'workspace'
            work.mkdir()
            for name in ('signals', 'slow_history', 'signals_candidates'):
                shutil.copytree(PARENT / 'workspace' / name, work / name)
            shutil.copyfile(PARENT / 'approved_cases.json', root / 'approved_cases.json')
            atomic_write_json(work / 'capability_backlog.json', read(PARENT / 'workspace/capability_backlog.json'))
            base._freeze_contract(root, contract)
            copied = {path.relative_to(work).as_posix(): binding(path)['sha256'] for name in ('signals', 'slow_history', 'signals_candidates')
                for path in sorted((work / name).rglob('*')) if path.is_file()}
            manifest = {'profile': 'assigned-slow-target-v1', 'target_need_ref': TARGET,
                'run_contract': contract.to_dict(), 'code': code, 'copied_files': copied,
                'reviewed_source': parent['reviewed_source'], 'first_wire': binding(first[0]),
                'source_bindings': [binding(PARENT / 'completion.json'), binding(base.CASES), binding(base.REVIEWED / 'reviewed_snapshot.json')],
                'accepted_memory_hash': read(PARENT / 'reflection-boundary.json')['slow_memory_hash'],
                'parent_target_acceptance': '0/1 retained; pre-first-Controller branch',
                'max_calls': 3, 'total_cap': TOTAL_CAP, 'request_cap': REQUEST_CAP}
            try:
                _construct(root, manifest, capture=True).run()
            except FrontierCaptured:
                pass
            else:
                raise base.StageRejected('native frontier did not reach first request')
            manifest['manifest_hash'] = digest(manifest)
            atomic_write_json(root / 'manifest.json', manifest)
            result = {'status': 'prepared_not_dispatched', 'manifest_hash': manifest['manifest_hash'], 'target_need_ref': TARGET}
            atomic_write_json(root / 'progress.json', result)
            return result
    except (Exception, base.EvolutionControlFlow) as error:
        return base._retained_failure(root, error)


def advance(root):
    """Run only the native Controller until pending or its first original sink."""
    root = _root(root)
    with base._lock(root):
        saved = base._terminal(root)
        if saved is not None:
            return saved
        try:
            manifest = _verify(root)
            with _guard(root):
                original = LabelAwareMiningController._execute
                def execute(controller, action, raw):
                    if action != 'record_need_dispositions' and not (action == 'inspect_catalog' and raw.get('scope') == 'backlog'):
                        raise base.StageRejected('action outside assigned Controller envelope')
                    value = original(controller, action, raw)
                    units = sorted((root / 'workspace/experiments/cycles/cycle-0001/mining_need_units').glob('*/*.json'))
                    if units:
                        base._immutable(root / 'controller-boundary.json', {'unit_files': [binding(p) for p in units],
                            'pending_need_refs': controller._pending_need_refs(), 'ledger': [row.to_dict() for row in controller.ledger.entries],
                            'backlog_hash': controller._backlog_hash, 'full_backlog_count': len(controller.backlog_needs)})
                        raise base.NeedProgressSaved('first original native sink write')
                    return value
                with patch.object(LabelAwareMiningController, '_execute', execute):
                    _construct(root, manifest).run()
                raise base.StageRejected('Controller returned without first sink boundary')
        except LocalRoleRequestPending as pending:
            _verify(root)
            result = {'status': 'pending', **pending.pending}
            atomic_write_json(root / 'progress.json', result)
            return result
        except base.NeedProgressSaved:
            _verify(root)
            return base._seal(root, {'status': 'native_need_unit_saved_semantics_unreviewed', 'target_need_ref': TARGET,
                'complete_S1_S2': False, 'completed_round': 0, 'completed_cycle': 0})
        except (Exception, base.EvolutionControlFlow) as error:
            return base._retained_failure(root, error)


def submit(root, request_hash, agent_id):
    """Attach a root-authorized independent raw response to the exact pending."""
    root = _root(root)
    with base._lock(root):
        if base._terminal(root) is not None:
            raise ValidationError('completed child cannot accept responses')
        _verify(root)
        value = read(root / 'progress.json')
        if value.get('status') != 'pending' or value.get('request_hash') != request_hash:
            raise ValidationError('submit requires exact pending request')
        if any(read(p)['agent_id'] == agent_id for p in (root / 'exchange/receipts').glob('*.json')):
            raise ValidationError('every response requires a fresh independent agent')
        return LocalRoleExchange(root / 'exchange', max_calls=3).submit(request_hash, agent_id=agent_id)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    op = parser.add_mutually_exclusive_group(required=True)
    op.add_argument('--prepare', action='store_true')
    op.add_argument('--advance', action='store_true')
    op.add_argument('--submit', action='store_true')
    parser.add_argument('--root', type=Path, default=ROOT)
    parser.add_argument('--request-hash'); parser.add_argument('--agent-id')
    args = parser.parse_args()
    result = prepare(args.root) if args.prepare else (submit(args.root, args.request_hash, args.agent_id) if args.submit else advance(args.root))
    print(json.dumps(result, sort_keys=True))


if __name__ == '__main__':
    main()
