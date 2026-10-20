"""Run the frozen, bounded native Slow reflection to need-progress module stage."""
from __future__ import annotations

import argparse
from contextlib import ExitStack, contextmanager
from copy import deepcopy
from datetime import datetime, timezone
import fcntl
import hashlib
import json
import os
from pathlib import Path
import shutil
import socket
import subprocess
import sys
from unittest.mock import patch

from stock_opportunity_agent.artifacts import atomic_write_json, canonical_json_hash as digest
from stock_opportunity_agent.cases.label_store import LabelStore
from stock_opportunity_agent.data.raw_info import RawInfoStore
from stock_opportunity_agent.data.reviewed_snapshot import open_raw_info_store
from stock_opportunity_agent.llm import get_model
from stock_opportunity_agent.models import ValidationError
from stock_opportunity_agent.research.evolution_control import (
    EvolutionRunContract, _historical_registry_snapshot, _rebased_history_meta_entries,
    validate_slow_history_manifest,
)
from stock_opportunity_agent.research.evolution_core import (
    EvolutionCase, GroundTruth, PlanMetaMemory, RoundMetaEntry,
)
from stock_opportunity_agent.research.evolution_signal_roles import LLMSignalMiningModel, LLMSignalUpdateModel
from stock_opportunity_agent.research.evolution_transport import ExternalAttemptLedger, StructuredRoleClient
from stock_opportunity_agent.research.local_role_exchange import (
    LocalRoleExchange, LocalRoleRequestPending,
)
from stock_opportunity_agent.research.mining_controller import LabelAwareMiningController
from stock_opportunity_agent.research.mining_role_model import MINING_CONTROLLER_STAGE
from stock_opportunity_agent.research.plan_evolution import EvolutionWorkspace
from stock_opportunity_agent.research.scheme_evolution import EvolutionControlFlow
from stock_opportunity_agent.research.signal_evolution import (
    SignalCandidateEffectivenessEvaluator, SignalCandidateValidator, SignalEvolutionEngine,
)
from stock_opportunity_agent.signal_library import SignalExecutor, SignalRegistry

REPO = Path(__file__).resolve().parents[1]
STAGE_ROOT = REPO / 'runs/diagnostics/reviewed_slow_feedback_stage_20261021_v1'
SPEC = REPO / 'spec/scripts/run_reviewed_slow_feedback_stage.md'
SOURCE = REPO / 'runs/diagnostics/reviewed_slow_history_export_20261021_v2'
SOURCE_SEAL_SHA = 'af51a017053d258b15b2bda7defcf73bbd86bf76c11b790e2fa2d4bff927352c'
HISTORY_HASH = 'ba60fd7c7aa4472900ef26c8068deee66e9d4e51c8a699455432f7eed626bc55'
CASES = REPO / 'runs/cold_start/minimal_rounds_v182_integrated/input_manifest.json'
CASES_SHA = '3c6a74fea9c3e29742d9759f11a9087cbb16726e17d509ec1f4dd7d5e2b48d3c'
OLD_CONTRACT = CASES.parent / 'run_contract.json'
REVIEWED = REPO / 'runs/diagnostics/reviewed_gpre_capture_snapshot_20261021_v1/stage/snapshot'
REVIEWED_SHA = '47546fc9029270e59a99353ac37e73857f0a3bf455ef54fe1428d836116e0c5a'
CONTROL = 'reflection:42597493a6b1af7ff10a07d6471c48610c0a21a1f24a18cbc9d0d11628abcd12'
MAX_CALLS, REQUEST_CAP, TOTAL_CAP = 8, 131072, 1048576
EXCLUDED = {'completion.json', '.stage.lock', 'exchange/.dispatch.lock'}


def read(path):
    """Read one saved JSON document without applying any derivatives."""
    return json.loads(Path(path).read_text(encoding='utf-8'))


def binding(path):
    """Return an absolute source identity bound to its exact bytes."""
    path = Path(path).resolve()
    return {'path': str(path), 'sha256': hashlib.sha256(path.read_bytes()).hexdigest()}


def _immutable(path, value):
    if path.exists():
        if read(path) != value:
            raise StageRejected(f'immutable stage artifact changed: {path.name}')
    else:
        atomic_write_json(path, value)


def _root(root):
    root = Path(root).resolve()
    if root != STAGE_ROOT.resolve():
        raise ValidationError('reviewed Slow stage destination is fixed')
    return root


class StageRejected(EvolutionControlFlow):
    """Terminal stage constraint, escaping native semantic-repair catch blocks."""


class NeedProgressSaved(EvolutionControlFlow):
    """Honest module boundary after the original progress sink, before next call."""


def _code():
    paths = {Path(__file__).resolve(), SPEC, REPO / 'tests/test_reviewed_slow_feedback_stage.py'}
    paths.update((REPO / 'src/stock_opportunity_agent').rglob('*.py'))
    paths.update((REPO / 'spec/src/stock_opportunity_agent').rglob('*.md'))
    return [binding(path) for path in sorted(paths)]


def _stage_contract():
    return {'schema_version': 'reviewed-slow-feedback-stage-v1', 'boundary': 'B',
            'root': str(STAGE_ROOT.resolve()), 'max_calls': MAX_CALLS,
            'per_request_logical_cap': REQUEST_CAP, 'total_logical_cap': TOTAL_CAP,
            'source_selectors': {'stage': 'slow_source_read', 'max': 3, 'output': 512, 'corrections': 0},
            'reflection': {'stage': 'signal_mining_reflect', 'first': 1, 'corrections': 1, 'output': 5000},
            'controller': {'stage': MINING_CONTROLLER_STAGE, 'regular': 2, 'corrections': 1, 'output': 4000},
            'controlled_native_page': True, 'reflection_item_ref': CONTROL,
            'external_llm_api_calls': 0, 'complete_cycle': False}


def _cases(value):
    if (value.get('schema_version') != 'diagnostic-development-subset-v1'
            or value.get('locked_test_accessed') is not False
            or set(value.get('splits', {})) != {'anchor', 'discovery', 'evolution_validation'}
            or {key: len(rows) for key, rows in value['splits'].items()}
            != {'anchor': 16, 'discovery': 16, 'evolution_validation': 8}):
        raise StageRejected('approved forty-case split/Locked Test boundary differs')
    restored = {}
    for name, rows in value['splits'].items():
        restored[name] = tuple(EvolutionCase(
            case_id=row['case_id'], company_id=row['company_id'],
            prediction_time=datetime.fromisoformat(row['prediction_time']),
            basic_info=row['basic_info'], ground_truth=GroundTruth.from_dict(row['ground_truth']))
            for row in rows)
    identities = tuple(case for rows in restored.values() for case in rows)
    if len({case.case_id for case in identities}) != 40:
        raise StageRejected('approved case identities repeat')
    return restored['discovery'], identities


def _history_authority():
    if binding(SOURCE / 'completed-files.json')['sha256'] != SOURCE_SEAL_SHA:
        raise StageRejected('sealed source completion identity differs')
    seal = read(SOURCE / 'completed-files.json')['files']
    actual = {path.relative_to(SOURCE / 'stage').as_posix(): binding(path)['sha256']
              for path in sorted((SOURCE / 'stage').rglob('*')) if path.is_file()}
    if len(actual) != 228 or actual != seal:
        raise StageRejected('sealed history file population/bytes differ')
    envelope = read(SOURCE / 'stage/slow_history/manifest.json')
    if envelope['manifest_hash'] != HISTORY_HASH or digest(envelope['manifest']) != HISTORY_HASH:
        raise StageRejected('approved history manifest differs')
    return envelope['manifest'], actual


def _footprint_preflight(history_root):
    """Reject this input if native direct footprints could disclose check outcomes."""
    rows = []
    for path in sorted(history_root.glob('*/experiments/cycles/*/slow_loop_validation.json')):
        validation = read(path).get('validation', {})
        metrics = validation.get('agent_audits', {}).get('mining_pipeline', {}).get('modality_metrics', {})
        outcomes = sum(isinstance(item, dict) and isinstance(item.get('candidate'), dict)
                       for item in validation.get('candidate_effectiveness', {}).values())
        rows.append({**binding(path), 'has_modality_metrics': bool(metrics),
                     'candidate_outcome_mappings': outcomes})
    if any(row['has_modality_metrics'] for row in rows):
        raise StageRejected('H1 prior-modality/check-outcome authorization is not proved')
    return rows


def _new_contract(history, cases, code):
    """Keep immutable research definitions; replace every operative execution cap."""
    old = read(OLD_CONTRACT)
    if digest(old['contract']) != old['contract_hash'] or old['contract_hash'] != history['source_contract_hash']:
        raise StageRejected('original contract source identity differs')
    value = deepcopy(old['contract'])
    registration = get_model('independent-subagent').to_public_dict()
    limits = dict(value['limits'])
    limits.update(plan_rounds_per_signal_cycle=0, candidates_per_round=1, top_k=1, random_k=0,
                  max_parallel_plans=1, max_signal_rounds=1, max_signal_calls=1, max_llm_calls=MAX_CALLS,
                  max_tokens=TOTAL_CAP, max_case_cost=0.01, max_agent_steps=MAX_CALLS,
                  max_request_tokens=REQUEST_CAP, max_case_tokens=TOTAL_CAP, max_case_llm_calls=MAX_CALLS,
                  max_local_role_calls=MAX_CALLS, max_structured_corrections=1,
                  structured_reasoning_token_reserve=0)
    value.update(run_id=STAGE_ROOT.name, created_at=datetime.now(timezone.utc).isoformat(),
                 dataset_manifest_hash=cases['approved_manifest_hash'],
                 raw_info_oracle_id='qualified-reviewed1780-module-stage',
                 raw_info_inventory_hash=REVIEWED_SHA, initial_signal_registry_version=history['registry_version'],
                 initial_signal_registry_hash=history['registry_hash'], limits=limits,
                 models={role: registration for role in ('judge', 'proposer', 'mining', 'update')},
                 code_revision=subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=REPO, text=True).strip()
                 + ':stage-code-' + digest(code), python_runtime=sys.version,
                 max_external_attempts=MAX_CALLS, max_total_cost=0.01,
                 cycle_mode='slow_only', slow_bootstrap_manifest_hash=None,
                 slow_history_manifest_hash=HISTORY_HASH, max_slow_cycles=1, min_new_signals_per_cycle=1,
                 parallel_jev_decisions=False, locked_test_accessed=False,
                 data_acquisition={})
    return EvolutionRunContract.from_dict(value)


@contextmanager
def _guard(root, *, protect_copies=True):
    """Confine runtime mutations and make prohibited expensive entrances fatal."""
    root = root.resolve()
    active = [True]
    previous_bytecode = sys.dont_write_bytecode
    sys.dont_write_bytecode = True

    def audit(event, args):
        if not active[0]:
            return
        if event in {'subprocess.Popen', 'os.system', 'os.posix_spawn'} or event.startswith('socket.'):
            raise StageRejected('stage network/subprocess entrance forbidden')
        paths = []
        if event == 'open':
            path, mode, flags = args
            if isinstance(path, (str, bytes, os.PathLike)):
                decoded = os.fsdecode(path)
                lower = decoded.lower()
                if Path(decoded).name in {'labels.jsonl', 'label_manifest.json'} or 'locked_test/' in lower:
                    raise StageRejected('global labels/Locked Test read forbidden')
                if (isinstance(mode, str) and any(char in mode for char in 'wax+')) or (
                        isinstance(flags, int) and flags & (os.O_WRONLY | os.O_RDWR | os.O_CREAT | os.O_TRUNC)):
                    paths = [path]
        elif event in {'os.mkdir', 'os.remove', 'os.rmdir', 'os.chmod', 'os.utime', 'os.truncate'}:
            paths = [args[0]]
        elif event in {'os.rename', 'os.link', 'os.symlink'}:
            paths = list(args[:2])
        for path in paths:
            if isinstance(path, int) or not Path(os.fsdecode(path)).resolve().is_relative_to(root):
                raise StageRejected('runtime write outside owned stage forbidden')
            resolved = Path(os.fsdecode(path)).resolve()
            if protect_copies and resolved in {root / 'run_contract.json', root / 'workspace/run_contract.json'}:
                raise StageRejected('frozen stage/workspace contract mutation forbidden')
            if protect_copies and any(resolved.is_relative_to(root / 'workspace' / name)
                    for name in ('signals', 'slow_history', 'signals_candidates')):
                if event == 'os.mkdir' and resolved.is_dir():
                    continue
                raise StageRejected('copied source Registry/history mutation forbidden')

    sys.addaudithook(audit)

    def forbidden(*args, **kwargs):
        raise StageRejected('stage forbids network/labels/Signal/candidate/publication/full Slow')

    with ExitStack() as stack:
        for target, name in ((socket, 'socket'), (socket, 'create_connection'),
                             (LabelStore, '__init__'), (LabelStore, 'load'), (LabelStore, 'ground_truth'),
                             (LabelStore, 'record'), (SignalExecutor, 'execute_batch'),
                             (SignalRegistry, 'freeze'), (SignalRegistry, 'audit_capabilities'),
                             (SignalRegistry, 'install_catalog'), (SignalRegistry, 'register_stable'),
                             (SignalRegistry, 'promote_candidates'), (SignalCandidateValidator, 'validate'),
                             (SignalCandidateEffectivenessEvaluator, 'evaluate'),
                             (SignalEvolutionEngine, 'run_cycle'), (EvolutionWorkspace, 'complete_cycle')):
            if hasattr(target, name):
                stack.enter_context(patch.object(target, name, forbidden))
        stack.enter_context(patch.object(RawInfoStore, 'append', forbidden))
        try:
            yield
        finally:
            active[0] = False
            sys.dont_write_bytecode = previous_bytecode


class _Budget:
    """Reconstruct unique exact-request reservations on every deterministic resume."""

    def __init__(self, request_root=None):
        self.requests = {}
        if request_root is not None:
            for path in sorted(request_root.glob('*.json')):
                saved = read(path)
                self._reserve(saved['request_hash'], saved['request'])

    def __call__(self, event):
        if event.get('event_type') != 'request_ready':
            return
        request = read(event['request_path'])['request']
        self._reserve(event['request_hash'], request)

    def _reserve(self, key, request):
        if key != digest(request):
            raise StageRejected('request hash differs')
        stage, output = request['stage'], request['max_output_tokens']
        if stage == 'slow_source_read' and output == 512:
            family, limit = 'selector', 3
        elif stage == 'signal_mining_reflect' and output == 5000:
            family, limit = 'reflection_first', 1
        elif stage in {'signal_mining_reflect_correction', 'signal_mining_reflect_patch_mechanics_correction'} and output == 5000:
            family, limit = 'reflection_correction', 1
        elif stage == MINING_CONTROLLER_STAGE and output == 4000:
            payload = json.loads(next(row['content'] for row in request['messages'] if row['role'] == 'user'))
            invalid = payload.get('last_invalid_action')
            family, limit = ('controller_correction', 1) if invalid else ('controller_regular', 2)
        else:
            raise StageRejected('stage/output/correction outside frozen B envelope')
        size = len(json.dumps(request['messages'], ensure_ascii=False, sort_keys=True,
                              separators=(',', ':')).encode('utf-8')) + output
        row = {'family': family, 'reservation': size}
        if key in self.requests:
            if self.requests[key] != row:
                raise StageRejected('replayed request reservation changed')
            return
        if (size > REQUEST_CAP or len(self.requests) >= MAX_CALLS
                or sum(item['reservation'] for item in self.requests.values()) + size > TOTAL_CAP
                or sum(item['family'] == family for item in self.requests.values()) >= limit):
            raise StageRejected('frozen unique request/family/logical cap exhausted')
        self.requests[key] = row


class _Caller:
    def __init__(self, client, budget, *, prepare=False):
        self.client, self.budget, self.prepare = client, budget, prepare

    def __getattr__(self, name):
        return getattr(self.client, name)

    def complete_json(self, **kwargs):
        if self.prepare:
            raise StageRejected('prepare may not request a model')
        if kwargs.get('stage') == MINING_CONTROLLER_STAGE:
            kwargs = {**kwargs, 'system_prompt': kwargs['system_prompt'] + (
                '\nThis frozen diagnostic module authorizes only inspect_catalog with scope=backlog '
                'and record_need_dispositions. An existing native backlog page has been read '
                'by a declared controlled initialization, not autonomous search. Keep unresolved '
                'needs pending. The stage stops after the first accepted native need progress '
                'write; do not perform candidate, evidence-fetch, statistic, terminal seed or '
                'other Mining actions. These execution limits supply no expected disposition.')}
        return self.client.complete_json(**kwargs)


def _verify_contracts(root, value):
    expected = {'contract': value, 'contract_hash': digest(value)}
    stage_path, workspace_path = root / 'run_contract.json', root / 'workspace/run_contract.json'
    if (read(stage_path) != expected or read(workspace_path) != expected
            or stage_path.read_bytes() != workspace_path.read_bytes()):
        raise StageRejected('stage/workspace frozen run contracts differ')


def _freeze_contract(root, contract):
    contract.freeze(root / 'run_contract.json')
    contract.freeze(root / 'workspace/run_contract.json')
    _verify_contracts(root, contract.to_dict())


def _construct(root, manifest, *, preparing=False):
    """Use actual constructors and the frozen production source qualification."""
    work = root / 'workspace'
    _verify_contracts(root, manifest['run_contract'])
    contract = EvolutionRunContract.load_frozen(work / 'run_contract.json')
    history = validate_slow_history_manifest(workspace=work, contract=contract)
    discovery, identities = _cases(read(root / 'approved_cases.json'))
    store = open_raw_info_store(REVIEWED, reviewed_snapshot=manifest['reviewed_source'])
    if len(store.documents) != 1780:
        raise StageRejected('qualified original document population differs')
    registry = SignalRegistry(work / 'signals', candidate_root=work / 'signals_candidates')
    snapshot = _historical_registry_snapshot(registry)
    if snapshot.version != history['registry_version'] or snapshot.registry_hash != history['registry_hash']:
        raise StageRejected('copied exact stable Registry differs')
    workspace = EvolutionWorkspace(work)
    workspace.start_or_resume_cycle(run_contract_hash=contract.contract_hash, target_plan_rounds=0,
        cycle_mode='slow_only', initial_signal_registry_version=snapshot.version,
        initial_signal_registry_hash=snapshot.registry_hash, observed_signal_registry_version=snapshot.version,
        observed_signal_registry_hash=snapshot.registry_hash, max_slow_cycles=1)
    if workspace.last_completed_round or workspace.last_completed_cycle:
        raise StageRejected('module workspace completed pointer advanced')
    meta = PlanMetaMemory(entries=_rebased_history_meta_entries(
        RoundMetaEntry.from_dict(row) for row in history['fast_context']['meta_entries']))
    budget = _Budget(root / 'transport/requests')
    client = StructuredRoleClient(registration=get_model('independent-subagent'), contract=contract,
        workspace=root / 'transport', local_role_exchange=LocalRoleExchange(root / 'exchange', max_calls=MAX_CALLS),
        ledger=ExternalAttemptLedger(root / 'unused_external_attempts.json', max_attempts=MAX_CALLS, max_total_cost=0.01),
        allow_external=False, environ={}, on_progress=budget)
    caller = _Caller(client, budget, prepare=preparing)
    engine = SignalEvolutionEngine(registry=registry, raw_info_store=store, discovery_cases=discovery,
        identity_cases=identities, workspace=workspace, meta_memory=meta,
        mining_model=LLMSignalMiningModel(caller), update_model=LLMSignalUpdateModel(caller),
        llm_signal_runner=None)
    return engine, snapshot, budget


def _preserved(root, manifest):
    _verify_contracts(root, manifest['run_contract'])
    actual = {path.relative_to(root / 'workspace').as_posix(): binding(path)['sha256']
              for name in ('signals', 'slow_history', 'signals_candidates')
              for path in sorted((root / 'workspace' / name).rglob('*')) if path.is_file()}
    if actual != manifest['copied_files']:
        raise StageRejected('copied immutable history/Registry population or bytes changed')
    state = read(root / 'workspace/state.json')
    cycle = read(root / 'workspace/cycle_state.json')
    if state.get('last_completed_round') != 0 or cycle.get('last_completed_cycle') != 0:
        raise StageRejected('module stage advanced a completed pointer')
    active = cycle.get('active_cycle')
    if not isinstance(active, dict) or active.get('cycle_id') != 1 or active.get('phase') != 'slow_loop':
        raise StageRejected('module active cycle boundary changed')
    ledger = read(root / 'unused_external_attempts.json')
    if ledger['attempts']:
        raise StageRejected('external attempt ledger must remain empty')


def _stage_files(root):
    return {path.relative_to(root).as_posix(): binding(path)['sha256']
            for path in sorted(root.rglob('*')) if path.is_file()
            and path.relative_to(root).as_posix() not in EXCLUDED}


def _seal(root, result):
    atomic_write_json(root / 'progress.json', result)
    _immutable(root / 'completion.json', {'result': result, 'files': _stage_files(root)})
    return result


def _terminal(root):
    if not (root / 'completion.json').is_file():
        return None
    saved = read(root / 'completion.json')
    if saved['files'] != _stage_files(root):
        raise ValidationError('terminal stage bytes changed')
    return saved['result']


def _verify(root):
    manifest = read(root / 'manifest.json')
    body = {key: value for key, value in manifest.items() if key != 'manifest_hash'}
    if digest(body) != manifest['manifest_hash'] or manifest['stage_contract'] != _stage_contract():
        raise StageRejected('frozen manifest/contract differs')
    if manifest['code'] != _code():
        raise StageRejected('prepared stage code/spec/tests changed')
    for row in manifest['source_bindings']:
        if binding(row['path']) != row:
            raise StageRejected('approved source bytes changed')
    _history_authority()
    for relative, sha in manifest['copied_files'].items():
        if binding(root / 'workspace' / relative)['sha256'] != sha:
            raise StageRejected('copied immutable history/Registry changed')
    if binding(root / 'approved_cases.json')['sha256'] != CASES_SHA:
        raise StageRejected('copied approved case bytes changed')
    _verify_contracts(root, manifest['run_contract'])
    _footprint_preflight(root / 'workspace/slow_history')
    return manifest


def prepare(root):
    """Freeze sources and a native input, without requesting or dispatching roles."""
    root = _root(root)
    if root.exists():
        raise ValidationError('stage root already exists; first setup is retained')
    root.mkdir(parents=True)
    try:
        history, _source_files = _history_authority()
        if binding(CASES)['sha256'] != CASES_SHA or binding(REVIEWED / 'reviewed_snapshot.json')['sha256'] != REVIEWED_SHA:
            raise StageRejected('approved case/reviewed source identity differs')
        cases = read(CASES)
        _cases(cases)
        if cases['approved_manifest_hash'] != history['dataset_manifest_hash']:
            raise StageRejected('approved dataset/history identity differs')
        code = _code()
        contract = _new_contract(history, cases, code)
        with _guard(root, protect_copies=False):
            work = root / 'workspace'
            work.mkdir()
            for name in ('signals', 'slow_history', 'signals_candidates'):
                shutil.copytree(SOURCE / 'stage' / name, work / name)
            shutil.copyfile(CASES, root / 'approved_cases.json')
            atomic_write_json(work / 'capability_backlog.json', history['fast_context']['capability_backlog_seed'])
            footprint = _footprint_preflight(work / 'slow_history')
            copied = {path.relative_to(work).as_posix(): binding(path)['sha256']
                      for name in ('signals', 'slow_history', 'signals_candidates') for path in sorted((work / name).rglob('*')) if path.is_file()}
            _freeze_contract(root, contract)
            manifest = {'stage_contract': _stage_contract(), 'run_contract': contract.to_dict(), 'code': code,
                'reviewed_source': {'root': str(REVIEWED.resolve()), 'manifest_sha256': REVIEWED_SHA, 'store_type': 'reviewed'},
                'source_bindings': [binding(CASES), binding(OLD_CONTRACT), binding(SOURCE / 'completed-files.json'),
                                    binding(REVIEWED / 'reviewed_snapshot.json')],
                'copied_files': copied, 'check_footprint_preflight': footprint}
            engine, snapshot, _budget = _construct(root, manifest, preparing=True)
            engine.workspace.refresh_capability_backlog(available_source_types=engine.evidence_resolver.available_source_types)
            slow_input = engine._prepare_slow_input(cycle_id=1, input_snapshot=snapshot)
            _preserved(root, manifest)
            actions, audit = engine._reflection_action_inventory()
            targets = [row for row in actions if row.get('reflection_item_ref') == CONTROL]
            if len(targets) != 1:
                raise StageRejected('native reflection action control missing or ambiguous')
            refs = [str(row['feedback_ref']) for row in slow_input['feedback_rows']]
            if len(refs) != len(set(refs)):
                raise StageRejected('native full feedback denominator repeats')
            manifest['native_prepared'] = {'slow_input_hash': digest(slow_input), 'full_feedback_count': len(refs),
                'feedback_refs_hash': digest(refs), 'source_manifest_hash': digest(slow_input['source_manifest']),
                'target_need_ref': targets[0]['need_ref'], 'target_action_hash': digest(targets[0]),
                'action_inventory_audit': audit, 'historical_pending': 3518, 'historical_processed': 0,
                'historical_imported_projection_not_full_D': 3531}
            manifest['manifest_hash'] = digest(manifest)
            atomic_write_json(root / 'manifest.json', manifest)
            result = {'status': 'prepared_not_dispatched', 'manifest_hash': manifest['manifest_hash'],
                      'full_feedback_count': len(refs), 'target_need_ref': targets[0]['need_ref']}
            atomic_write_json(root / 'progress.json', result)
            return result
    except (Exception, EvolutionControlFlow) as error:
        failure = {'status': 'preflight_failed_no_dispatch', 'error_type': type(error).__name__, 'error': str(error)}
        atomic_write_json(root / 'failure.json', failure)
        return _seal(root, failure)


@contextmanager
def _controller_boundary(root, manifest):
    """Keep original Controller and sink; intercept only stage admission and stop."""
    original_init, original_execute = LabelAwareMiningController.__init__, LabelAwareMiningController._execute
    target = manifest['native_prepared']['target_need_ref']

    def initialize(controller, *args, **kwargs):
        if kwargs.get('seed') != 'hypothesis':
            raise StageRejected('second Controller seed forbidden')
        original_init(controller, *args, **kwargs)
        _immutable(root / 'factory-input.json', {
            'factory': 'SignalEvolutionEngine._run_controller_mining_axis',
            'seed': controller.seed, 'case_count': len(controller.case_pairs),
            'backlog_needs': list(controller.backlog_needs),
            'meta_memory_briefs': controller.meta_memory_briefs,
            'meta_memory_disclosures': list(controller.meta_memory_disclosures),
            'slow_method_memory': controller.slow_method_memory,
            'prior_modality_footprints': list(controller.prior_modality_footprints),
            'research_axis': controller.research_axis,
            'label_map': controller._label_map})
        matches = [index for index, row in enumerate(controller.backlog_needs) if row['need_ref'] == target]
        if len(matches) != 1:
            raise StageRejected('prepared native need absent from full factory backlog')
        page = controller._backlog_view(cursor=matches[0])
        if target not in {row['need_ref'] for row in page['items']}:
            raise StageRejected('native target page cannot disclose whole control')
        _immutable(root / 'controlled-page.json', {'controlled_read_not_autonomous_search': True,
            'cursor': matches[0], 'target_need_ref': target, 'backlog_count': len(controller.backlog_needs),
            'backlog_hash': controller._backlog_hash, 'backlog_rows_hash': digest(list(controller.backlog_needs)),
            'page_hash': digest(page)})
        original_execute(controller, 'inspect_catalog', {'action': 'inspect_catalog', 'scope': 'backlog',
                         'cursor': matches[0], 'rationale': ['Stage-authorized controlled native page initialization.']})
        _immutable(root / 'controlled-page-read.json', {'tool_result': controller._last_action_result,
            'ledger': [row.to_dict() for row in controller.ledger.entries]})

    def execute(controller, action, raw):
        if action != 'record_need_dispositions' and not (action == 'inspect_catalog' and raw.get('scope') == 'backlog'):
            raise StageRejected('Controller action outside bounded stage envelope')
        value = original_execute(controller, action, raw)
        units = list((root / 'workspace/experiments/cycles/cycle-0001/mining_need_units').glob('*/*.json'))
        if units:
            # The unmodified production save_need_unit has already returned.
            _immutable(root / 'controller-boundary.json', {'module_status': 'partial_running',
                'stop': 'after_original_need_progress_sink', 'unit_files': [binding(path) for path in sorted(units)],
                'ledger': [row.to_dict() for row in controller.ledger.entries],
                'pending_need_refs': controller._pending_need_refs(),
                'backlog_hash': controller._backlog_hash, 'full_backlog_count': len(controller.backlog_needs)})
            raise NeedProgressSaved('original need progress persisted; module boundary reached')
        return value

    with patch.object(LabelAwareMiningController, '__init__', initialize), patch.object(LabelAwareMiningController, '_execute', execute):
        yield


@contextmanager
def _lock(root):
    with (root / '.stage.lock').open('a+', encoding='utf-8') as handle:
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


def _retained_failure(root, error):
    failure = {'status': 'failed', 'error_type': type(error).__name__, 'error': str(error)}
    atomic_write_json(root / 'failure.json', failure)
    return _seal(root, failure)


def advance(root):
    """Advance the original native modules until one pending request or boundary."""
    root = _root(root)
    with _lock(root):
        terminal = _terminal(root)
        if terminal is not None:
            return terminal
        try:
            manifest = _verify(root)
            with _guard(root):
                engine, snapshot, budget = _construct(root, manifest)
                slow_input = engine._prepare_slow_input(cycle_id=1, input_snapshot=snapshot)
                if digest(slow_input) != manifest['native_prepared']['slow_input_hash']:
                    raise StageRejected('prepared native input changed')
                memory = engine._prepare_slow_memory(cycle_id=1, slow_input=slow_input)
                processed, pending_refs = set(memory['processed_feedback_refs']), set(memory['pending_feedback_refs'])
                full = {row['feedback_ref'] for row in slow_input['feedback_rows']}
                if processed & pending_refs or processed | pending_refs != full:
                    raise StageRejected('native memory full denominator partition differs')
                if memory['status'] not in {'appended', 'no_new_lesson'}:
                    raise StageRejected('native reflection did not persist success: ' + str(memory.get('failure_ref')))
                engine._active_slow_input, engine._active_slow_memory = slow_input, memory
                engine._active_sampling_manifest = slow_input['sampling_manifest']
                _immutable(root / 'reflection-boundary.json', {'slow_input_hash': digest(slow_input),
                    'slow_memory_hash': digest(memory), 'full_feedback_count': len(full),
                    'processed_count': len(processed), 'pending_count': len(pending_refs),
                    'module_status': memory['status']})
                dev, check = engine._manifest_cases('dev_case_ids'), engine._manifest_cases('check_case_ids')
                labels = {case.case_id: 'positive' if case.ground_truth.is_surge else 'control' for case in (*dev, *check)}
                with _controller_boundary(root, manifest):
                    engine._run_controller_mining_axis(cycle_id=1, axis_id='surge_direction',
                        research_axis={'axis_id': 'surge_direction', 'population': 'eligible_discovery_cases',
                                       'positive': 'realized_max_multiple >= 2.0', 'control': 'realized_max_multiple < 2.0'},
                        dev_cases=dev, check_cases=check, labels_by_case_id=labels)
                raise StageRejected('factory returned without the required module boundary')
        except LocalRoleRequestPending as waiting:
            try:
                _preserved(root, manifest)
            except (Exception, EvolutionControlFlow) as error:
                return _retained_failure(root, error)
            result = {'status': 'pending', **waiting.pending}
            atomic_write_json(root / 'progress.json', result)
            return result
        except NeedProgressSaved:
            try:
                _preserved(root, manifest)
            except (Exception, EvolutionControlFlow) as error:
                return _retained_failure(root, error)
            return _seal(root, {'status': 'native_need_unit_saved_semantics_unreviewed',
                'module_status': 'partial_running', 'completed_round': 0, 'completed_cycle': 0,
                'external_llm_api_calls': 0, 'complete_S1_S2': False})
        except (Exception, EvolutionControlFlow) as error:
            return _retained_failure(root, error)


def pending(root):
    """Inspect the current pending envelope without executing any native work."""
    root = _root(root)
    with _lock(root):
        terminal = _terminal(root)
        if terminal is not None:
            return terminal
        _verify(root)
        return read(root / 'progress.json')


def submit(root, request_hash, agent_id):
    """Attach one actual fresh agent receipt; never author or edit its answer."""
    root = _root(root)
    with _lock(root):
        if _terminal(root) is not None:
            raise ValidationError('terminal stage accepts no response')
        _verify(root)
        current = read(root / 'progress.json')
        if current.get('status') != 'pending' or current.get('request_hash') != request_hash:
            raise ValidationError('submit requires the exact current pending request')
        receipts = [read(path) for path in (root / 'exchange/receipts').glob('*.json')]
        if any(row['agent_id'] == agent_id for row in receipts):
            raise ValidationError('each original response requires a distinct fresh agent')
        return LocalRoleExchange(root / 'exchange', max_calls=MAX_CALLS).submit(request_hash, agent_id=agent_id)


def main():
    """Expose preparation, bounded advancement and exact receipt operations."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=('prepare', 'advance', 'pending', 'submit'))
    parser.add_argument('--root', type=Path, default=STAGE_ROOT)
    parser.add_argument('--request-hash')
    parser.add_argument('--agent-id')
    args = parser.parse_args()
    if args.command == 'submit':
        if not args.request_hash or not args.agent_id:
            parser.error('submit requires --request-hash and --agent-id')
        result = submit(args.root, args.request_hash, args.agent_id)
    else:
        result = globals()[args.command](args.root)
    print(json.dumps(result, ensure_ascii=False, sort_keys=True, indent=2))


if __name__ == '__main__':
    main()
