"""Prepare or run a diagnostic Fast+Slow or committed-Fast bootstrap cycle.

Usage: PYTHONPATH=src python scripts/run_minimal_rounds.py --root RUN --prepare-only
       PYTHONPATH=src python scripts/run_minimal_rounds.py --root RUN --run
       Add --slow-bootstrap-from SOURCE to reuse an exact committed Fast range.
       Add --slow-history-from SOURCE to continue a committed Slow publication.

The first command freezes source-derived inputs without model calls. The second
requires authorization for external execution and a committed source checkout.
Both preserve the same frozen denominator; failures never become fake research.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
from collections import defaultdict
from dataclasses import replace
from datetime import datetime
from pathlib import Path

from stock_opportunity_agent.artifacts import atomic_write_json, canonical_json_hash
from stock_opportunity_agent.cases.label_store import LabelStore
from stock_opportunity_agent.data.raw_info import RawInfoDocument, RawInfoOracle, RawInfoStore
from stock_opportunity_agent.data.reviewed_snapshot import open_raw_info_store
from stock_opportunity_agent.data.resolution import broad_research_data_policy_v1, DataAcquisitionPolicy
from stock_opportunity_agent.llm import get_model
from stock_opportunity_agent.models import ValidationError
from stock_opportunity_agent.research.evolution_control import (
    ApprovedDevelopmentDataset, EvolutionRunContract, _build_evidence_resolver,
    _default_priors_dict, build_run_contract, load_approved_development_dataset,
    _rebased_history_meta_entries, apply_slow_bootstrap_derivatives,
    build_slow_bootstrap_manifest, validate_slow_bootstrap_manifest,
    build_slow_history_manifest, validate_slow_history_manifest, apply_slow_history_manifest,
    _registry_matches_committed_history,
)
from stock_opportunity_agent.research.evolution_core import (
    EVALUATION_LABELS, EvolutionCase, GroundTruth, PlanEvaluationConfig, PlanMetaMemory, RoundMetaEntry,
    RuntimeLimits, _prediction_baseline_from_market_documents,
    default_information_plan, evaluation_label,
)
from stock_opportunity_agent.research.evolution_plan_roles import (
    LLMBlindPredictor, LLMInformationPlanProposer, LLMPlanCritic,
    LLMResearchController, LLMRoundReflector, LLMSignalRetrievalAgent,
)
from stock_opportunity_agent.research.evolution_signal_roles import (
    LLMSignalMiningModel, LLMSignalUpdateModel, StructuredLLMSignalRunner,
)
from stock_opportunity_agent.research.evolution_transport import (
    ExternalAttemptLedger, StructuredRoleClient, current_code_revision,
)
from stock_opportunity_agent.research.plan_evolution import (
    EvolutionWorkspace, PlanEvolutionEngine, RuntimePlanEvaluator,
)
from stock_opportunity_agent.research.research_targets import (
    MAGNITUDE_GE3_CONTRACT, build_target_group_manifest,
    build_target_sampling_manifest,
)
from stock_opportunity_agent.research.signal_evolution import (
    DualLoopEvolutionEngine, SignalEvolutionEngine,
)
from stock_opportunity_agent.signal_library import SignalRegistry

REPO = Path(__file__).resolve().parent.parent
ORACLE = REPO / 'runs/cold_start/data/global-raw-info-oracle-v1'
LABELS = REPO / 'runs/cold_start/data/outcome-label-store-v1'
APPROVED = REPO / ('runs/cold_start/evolution/full-market-expanded-2025plus-v13-approved-inputs/'
                   'expanded_dataset_proposal/dataset_manifest.approved.json')
HISTORY = REPO / ('runs/cold_start/evolution/'
                  'information-evolution-jev-dual-self-evolution-20260928-v143')
SOURCE_REVIEW = REPO / 'reports/raw-info-source-integrity-review-20261001.json'


def _read(path):
    return json.loads(Path(path).read_text(encoding='utf-8'))


def _hash_file(path):
    digest = hashlib.sha256()
    with Path(path).open('rb') as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b''):
            digest.update(chunk)
    return digest.hexdigest()


def _load_env():
    """Load provider configuration without logging credential values."""
    path = REPO / '.env.local'
    if path.is_file():
        for line in path.read_text().splitlines():
            if '=' in line and not line.lstrip().startswith('#'):
                key, value = line.split('=', 1)
                os.environ.setdefault(key.strip(), value.strip())


def _evaluation():
    return PlanEvaluationConfig()


def _restore_case(row):
    return EvolutionCase(
        case_id=row['case_id'], company_id=row['company_id'],
        prediction_time=datetime.fromisoformat(row['prediction_time']),
        basic_info=row['basic_info'], ground_truth=GroundTruth.from_dict(row['ground_truth']),
    )


def _verify_inputs(root):
    frozen = _read(root / 'input_manifest.json')
    reviewed = frozen.get('reviewed_source_snapshot')
    if reviewed is not None:
        store = open_raw_info_store(reviewed['root'], reviewed_snapshot=reviewed)
        if {row['source_path'] for row in frozen['source_files']} != {
                str(path) for path in (store.root / 'documents').glob('*.json')}:
            raise ValidationError('reviewed frozen source file membership differs')
    elif any(not Path(row['source_path']).resolve().is_relative_to(ORACLE.resolve())
             for row in frozen['source_files']):
        raise ValidationError('plain frozen sources must belong to the canonical oracle; reviewed binding missing')
    if _hash_file(APPROVED) != frozen['approved_manifest_hash']:
        raise ValidationError('approved input manifest changed')
    if _hash_file(LABELS / 'manifest.json') != frozen['label_manifest_hash']:
        raise ValidationError('label manifest changed')
    if _hash_file(LABELS / 'labels.jsonl') != frozen['label_records_hash']:
        raise ValidationError('label records changed')
    if _hash_file(SOURCE_REVIEW) != frozen['source_integrity_review_hash']:
        raise ValidationError('source integrity review changed')
    for row in frozen['source_files']:
        path = Path(row['source_path'])
        if _hash_file(path) != row['sha256']:
            raise ValidationError(f'frozen Raw Info changed: {row["source_path"]}')
    return frozen


def _development_dataset(frozen):
    """Restore the previously frozen approved subset, never resample on resume."""
    return ApprovedDevelopmentDataset(**{key: tuple(_restore_case(row) for row in rows)
        for key, rows in frozen['splits'].items()}, locked_test_hash=frozen['locked_test_hash'],
        approved_manifest_hash=frozen['approved_manifest_hash'])


def prepare(root, *, seed_registry: Path | None = None, slow_bootstrap_from: Path | None = None,
            slow_history_from: Path | None = None, reviewed_source_snapshot: Path | None = None):
    """Freeze stratified development cases before any model observation."""
    if sum(item is not None for item in (seed_registry, slow_bootstrap_from, slow_history_from)) > 1:
        raise ValidationError('seed, bootstrap and committed history sources are mutually exclusive')
    bootstrap_source = None if slow_bootstrap_from is None else slow_bootstrap_from.resolve()
    history_source = None if slow_history_from is None else slow_history_from.resolve()
    source_root = bootstrap_source or history_source
    reviewed = _read(reviewed_source_snapshot) if reviewed_source_snapshot is not None else None
    reviewed_store = None if reviewed is None else open_raw_info_store(reviewed['root'], reviewed_snapshot=reviewed)
    registry_source = ((source_root / 'signals') if source_root is not None
                       else (seed_registry or HISTORY / 'signals')).resolve()
    root.mkdir(parents=True, exist_ok=True)
    if (root / 'input_manifest.json').is_file():
        frozen = _verify_inputs(root)
        if reviewed is not None and reviewed != frozen.get('reviewed_source_snapshot'):
            raise ValidationError('requested reviewed source differs from frozen inputs')
        if seed_registry is not None and registry_source != Path(frozen['registry_source']).resolve():
            raise ValidationError('requested Registry seed differs from prepared inputs; use a successor workspace')
        if bootstrap_source is not None and str(bootstrap_source) != frozen.get('slow_bootstrap_source'):
            raise ValidationError('requested bootstrap source differs from prepared inputs; use a successor workspace')
        if history_source is not None and str(history_source) != frozen.get('slow_history_source'):
            raise ValidationError('requested history source differs from prepared inputs; use a successor workspace')
        return frozen
    if (root / 'run_contract.json').exists() or (root / 'state.json').exists():
        raise ValidationError('cannot retrofit inputs into an existing run')
    if not (registry_source / 'registry.json').is_file():
        raise ValidationError('diagnostic Registry seed requires existing registry.json')
    if (root / 'signals').exists():
        raise ValidationError('partial diagnostic Registry exists without frozen inputs; use a successor workspace')
    if history_source is not None:
        source = _verify_inputs(history_source)
        if reviewed is not None and reviewed != source.get('reviewed_source_snapshot'):
            raise ValidationError('reviewed source cannot replace inherited history inputs')
        manifest_hash = build_slow_history_manifest(workspace=root, source_workspace=history_source,
            dataset_manifest_hash=source['approved_manifest_hash'])
        manifest = _read(root / 'slow_history' / 'manifest.json')['manifest']
        apply_slow_history_manifest(workspace=root, manifest=manifest)
        snapshot = SignalRegistry(root / 'signals', candidate_root=root / 'signals_candidates').freeze()
        frozen = {key: value for key, value in source.items() if key not in (
            'slow_bootstrap_source', 'slow_bootstrap_manifest_hash', 'slow_history_source',
            'slow_history_manifest_hash', 'source_input_manifest_sha256')}
        frozen.update(registry_source=str(registry_source), initial_registry_version=snapshot.version,
            initial_registry_hash=snapshot.registry_hash, initial_registry_refs=[spec.ref for spec in snapshot.specs],
            slow_history_source=str(history_source), slow_history_manifest_hash=manifest_hash,
            source_input_manifest_sha256=_hash_file(history_source / 'input_manifest.json'))
        atomic_write_json(root / 'input_manifest.json', frozen)
        return frozen
    if bootstrap_source is not None:
        source = _verify_inputs(bootstrap_source)
        if reviewed is not None and reviewed != source.get('reviewed_source_snapshot'):
            raise ValidationError('reviewed source cannot replace inherited bootstrap inputs')
        if EvolutionWorkspace(bootstrap_source).last_completed_round < 1:
            raise ValidationError('diagnostic bootstrap requires committed Fast input')
        shutil.copytree(registry_source, root / 'signals',
            ignore=shutil.ignore_patterns('learning', 'stats.json', 'events.jsonl', 'profile.json', '.transitions'))
        snapshot = SignalRegistry(root / 'signals', candidate_root=root / 'signals_candidates').freeze()
        manifest_hash = build_slow_bootstrap_manifest(workspace=root,
            source_workspaces=(bootstrap_source,), dataset=_development_dataset(source),
            signal_snapshot=snapshot, evaluation_contract=source['evaluation'])
        frozen = {**source, 'registry_source': str(registry_source),
            'initial_registry_version': snapshot.version, 'initial_registry_hash': snapshot.registry_hash,
            'initial_registry_refs': [spec.ref for spec in snapshot.specs],
            'slow_bootstrap_source': str(bootstrap_source), 'slow_bootstrap_manifest_hash': manifest_hash,
            'source_input_manifest_sha256': _hash_file(bootstrap_source / 'input_manifest.json')}
        atomic_write_json(root / 'input_manifest.json', frozen)
        return frozen
    approved = load_approved_development_dataset(APPROVED)
    labels = LabelStore.load(LABELS)
    review = _read(SOURCE_REVIEW)
    if review.get('schema_version') != 'diagnostic-source-integrity-review-v1':
        raise ValidationError('unsupported diagnostic source review')
    unproven_sources = {row['document_id']: row for row in review['reviews']
                        if row['verdict'] == 'issuer_identity_unproven'}
    files_by_company = defaultdict(list)
    if reviewed_store is not None:
        for source in sorted((reviewed_store.root / 'documents').glob('*.json')):
            document = RawInfoDocument.from_dict(_read(source))
            files_by_company[document.company_id].append(source)
    else:
        for family in sorted(ORACLE.iterdir()):
            if family.is_dir():
                for company in sorted(family.iterdir()):
                    if company.is_dir():
                        files_by_company[company.name].extend(sorted(company.glob('*.json')))
    market_cache = {}
    document_cache = {}
    exclusions = []
    baseline_comparisons = []
    selected = {}
    # Scope and seed are fixed; no score, model confidence or correction result
    # exists when this selection runs. Strata retain the established semantics.
    for split, targets in (
            ('anchor', dict(_evaluation().anchor_label_counts)),
            ('evolution_validation', dict(_evaluation().random_label_counts)),
            ('discovery', {'non_surge': 8, '2_3x': 4, '3_10x': 2, '10x_plus': 2})):
        candidates = sorted(getattr(approved, split), key=lambda case:
                            hashlib.sha256(('42:' + case.case_id).encode()).hexdigest())
        groups = defaultdict(list)
        issuers = set()
        for original in candidates:
            try:
                truth = labels.ground_truth(original.company_id, original.prediction_time.date())
            except ValidationError:
                exclusions.append({'split': split, 'case_id': original.case_id,
                                   'reason': 'label_store_key_unavailable'})
                continue
            case = replace(original, ground_truth=GroundTruth(
                realized_max_multiple=truth['realized_max_multiple']))
            group = evaluation_label(case)
            if len(groups[group]) >= targets[group] or case.company_id in issuers:
                continue
            if case.company_id not in market_cache:
                document_cache[case.company_id] = tuple(RawInfoDocument.from_dict(_read(path))
                    for path in files_by_company[case.company_id])
                market_cache[case.company_id] = tuple(document
                    for document in document_cache[case.company_id]
                    if document.source_type in {'historical_price', 'market_data', 'price_daily', 'prices'})
            unproven = [document.document_id for document in market_cache[case.company_id]
                        if document.available_at <= case.prediction_time
                        and document.document_id in unproven_sources
                        and document.content_hash == unproven_sources[document.document_id]['content_hash']]
            if unproven:
                exclusions.append({'split': split, 'case_id': case.case_id,
                                   'reason': 'price_source_issuer_identity_unproven',
                                   'document_refs': unproven, 'review_ref': str(SOURCE_REVIEW)})
                continue
            baseline = _prediction_baseline_from_market_documents(
                (document for document in market_cache[case.company_id]
                 if document.available_at <= case.prediction_time), case.prediction_time)
            if baseline.get('status') != 'available':
                exclusions.append({'split': split, 'case_id': case.case_id,
                                   'reason': 'pit_price_baseline_unavailable'})
                continue
            # Bind the same dates. Provider adjustment/rounding conventions may
            # differ; do not import retrospective label prices into blind input.
            record = labels.record(case.company_id, case.prediction_time.date())
            if tuple(baseline['trading_dates']) != record.baseline_dates:
                exclusions.append({'split': split, 'case_id': case.case_id,
                                   'reason': 'source_label_baseline_dates_mismatch'})
                continue
            has_narrative = any(document.source_type in {'sec_filing', 'filing', 'earnings_call', 'news', 'company_news'}
                                and document.available_at <= case.prediction_time
                                for document in document_cache[case.company_id])
            if not has_narrative:
                exclusions.append({'split': split, 'case_id': case.case_id,
                                   'reason': 'pit_narrative_unavailable'})
                continue
            groups[group].append(case)
            baseline_comparisons.append({'split': split, 'case_id': case.case_id,
                                         'source_mean': baseline['mean_adjusted_close'],
                                         'label_mean': record.baseline_mean,
                                         'relative_difference': baseline['mean_adjusted_close']/record.baseline_mean-1,
                                         'same_baseline_dates': True,
                                         'blind_label_price_substitution': False})
            issuers.add(case.company_id)
            print(f'  select {split}: {case.case_id} [{group}]', flush=True)
            if all(len(groups[label]) == targets[label] for label in EVALUATION_LABELS):
                break
        missing = {label: targets[label]-len(groups[label]) for label in EVALUATION_LABELS
                   if len(groups[label]) < targets[label]}
        if missing:
            atomic_write_json(root / 'preparation_failure.json', {'split': split, 'missing': missing,
                'exclusions': exclusions, 'reviewed_source_snapshot': reviewed})
            raise ValidationError(f'approved source-ready subset insufficient: {split} {missing}')
        selected[split] = [case.to_discovery_dict() for label in EVALUATION_LABELS for case in groups[label]]
    companies = {row['company_id'] for rows in selected.values() for row in rows}
    source_files = []
    for company_id in sorted(files_by_company if reviewed_store is not None else companies):
        for source in files_by_company[company_id]:
            source_files.append({'source_path': str(source), 'sha256': _hash_file(source)})
    registry_root = root / 'signals'
    shutil.copytree(registry_source, registry_root)
    registry = SignalRegistry(registry_root, candidate_root=root / 'signals_candidates').freeze()
    frozen = {
        'schema_version': 'diagnostic-development-subset-v1',
        'approved_manifest_hash': approved.approved_manifest_hash,
        'label_manifest_hash': _hash_file(LABELS / 'manifest.json'),
        'label_records_hash': _hash_file(LABELS / 'labels.jsonl'),
        'source_integrity_review_hash': _hash_file(SOURCE_REVIEW),
        'locked_test_hash': approved.locked_test_hash, 'locked_test_accessed': False,
        'selection_seed': 42, 'selection_before_model_calls': True,
        'evaluation': _evaluation().to_dict(), 'splits': selected,
        'exclusions': exclusions, 'source_files': source_files,
        'baseline_comparisons': baseline_comparisons,
        'initial_registry_version': registry.version, 'initial_registry_hash': registry.registry_hash,
        'registry_source': str(registry_source), 'paired_with_v154': False,
    }
    if reviewed is not None:
        frozen['reviewed_source_snapshot'] = reviewed
    atomic_write_json(root / 'input_manifest.json', frozen)
    return frozen


def run(root, frozen):
    """Execute and resume the actual production cycle, preserving control failures."""
    reviewed = frozen.get('reviewed_source_snapshot')
    source_root = ORACLE if reviewed is None else Path(reviewed['root'])
    store = open_raw_info_store(source_root, reviewed_snapshot=reviewed)
    _load_env()
    workspace = EvolutionWorkspace(root)
    if workspace.last_completed_cycle >= 1:
        print('The bounded diagnostic cycle is already committed.', flush=True)
        return
    registry = SignalRegistry(root / 'signals', candidate_root=root / 'signals_candidates')
    initial = registry.freeze()
    dataset = _development_dataset(frozen)
    bootstrap_hash = frozen.get('slow_bootstrap_manifest_hash')
    history_hash = frozen.get('slow_history_manifest_hash')
    cycle_mode = 'slow_bootstrap' if bootstrap_hash is not None else 'fast_then_slow'
    target_plan_rounds = 0 if bootstrap_hash is not None else 1
    oracle = RawInfoOracle.load_or_create(source_root)
    contract_path = root / 'run_contract.json'
    if contract_path.exists():
        contract = EvolutionRunContract.from_dict(_read(contract_path)['contract'])
        if contract.limits.get('reviewed_source_snapshot') != reviewed:
            raise ValidationError('run reviewed source binding differs from frozen inputs')
        if contract.code_revision != current_code_revision(REPO):
            raise ValidationError('run source revision changed; use a successor workspace')
        if contract.raw_info_inventory_hash != canonical_json_hash(frozen):
            raise ValidationError('run diagnostic inputs changed')
        if (contract.cycle_mode != cycle_mode or contract.slow_bootstrap_manifest_hash != bootstrap_hash
                or contract.slow_history_manifest_hash != history_hash):
            raise ValidationError('run diagnostic mode changed')
        contract.freeze(contract_path)
    else:
        if (initial.version, initial.registry_hash) != (
                frozen['initial_registry_version'], frozen['initial_registry_hash']):
            raise ValidationError('prepared Registry changed before run freeze')
        limits = dict(_read(HISTORY / 'run_contract.json')['contract']['limits'])
        limits.update(evaluation=_evaluation().to_dict(), candidates_per_round=2,
                      max_parallel_plans=1, max_structured_corrections=1,
                      plan_rounds_per_signal_cycle=target_plan_rounds)
        if reviewed is not None:
            limits['reviewed_source_snapshot'] = reviewed
        # Model registries and exact-request transport own wire settings and cost.
        contract = build_run_contract(
            run_id=root.name, dataset_manifest_path=APPROVED, inventory=None,
            raw_info_oracle=oracle, raw_info_inventory_hash=canonical_json_hash(frozen),
            initial_signal_registry_version=initial.version,
            initial_signal_registry_hash=initial.registry_hash,
            priors=_default_priors_dict(), role_aliases={role: 'deepseek-v4-flash' for role in
                ('judge', 'proposer', 'mining', 'update')}, project_root=REPO,
            limits=limits, max_external_attempts=1200, max_total_cost=100,
            data_acquisition=broad_research_data_policy_v1() if reviewed is None else DataAcquisitionPolicy(),
            cycle_mode=cycle_mode, slow_bootstrap_manifest_hash=bootstrap_hash,
            slow_history_manifest_hash=history_hash,
        )
        contract.freeze(contract_path)
    cycle = workspace.start_or_resume_cycle(
        run_contract_hash=contract.contract_hash, target_plan_rounds=target_plan_rounds,
        cycle_mode=contract.cycle_mode, max_slow_cycles=contract.max_slow_cycles,
        initial_signal_registry_version=contract.initial_signal_registry_version,
        initial_signal_registry_hash=contract.initial_signal_registry_hash,
        observed_signal_registry_version=initial.version, observed_signal_registry_hash=initial.registry_hash,
    )
    staged = workspace.staged_slow_result(cycle['cycle_id'])
    if staged is not None:
        workspace.complete_cycle(cycle_id=cycle['cycle_id'],
                                 observed_signal_registry_version=initial.version,
                                 observed_signal_registry_hash=initial.registry_hash)
        print('Reused staged Slow result and committed its pointer.', flush=True)
        return
    bootstrap_entries = ()
    if bootstrap_hash is not None:
        seed_snapshot = registry.snapshot_from_refs(frozen['initial_registry_version'],
            tuple(frozen['initial_registry_refs']))
        manifest = validate_slow_bootstrap_manifest(workspace=root, contract=contract,
            signal_snapshot=seed_snapshot)
        bootstrap_entries = _rebased_history_meta_entries(
            apply_slow_bootstrap_derivatives(manifest, registry=registry))
    elif history_hash is not None:
        manifest = validate_slow_history_manifest(workspace=root, contract=contract)
        if not _registry_matches_committed_history(snapshot_version=initial.version,
                snapshot_hash=initial.registry_hash, history_registry_version=int(manifest['registry_version']),
                history_registry_hash=str(manifest['registry_hash']), workspace_root=root):
            raise ValidationError('diagnostic Registry differs from committed history chain')
        bootstrap_entries = _rebased_history_meta_entries(
            RoundMetaEntry.from_dict(dict(row)) for row in manifest['fast_context']['meta_entries'])
    def emit(event):
        event = dict(event)
        event_type = event.pop('event_type', 'runtime_progress')
        if event_type == 'slow_loop_started':
            workspace.mark_cycle_phase('slow_loop')
        workspace.append_event(event_type, event)
        print(json.dumps({'event': event_type, **{key: event[key] for key in
                         ('stage', 'case_id', 'plan_id', 'round_id', 'reason') if key in event}},
                         ensure_ascii=False), flush=True)
    ledger = ExternalAttemptLedger(root / 'attempts.json', max_attempts=contract.max_external_attempts,
                                   max_total_cost=contract.max_total_cost)
    ledger.reconcile_interrupted()
    caller = StructuredRoleClient(
        registration=get_model('deepseek-v4-flash'), contract=contract, workspace=root,
        ledger=ledger, allow_external=True, acknowledged_contract_hash=contract.contract_hash,
        on_progress=emit,
    )
    resolver = _build_evidence_resolver(root, store, contract=contract, allow_data_external=reviewed is None,
                                        environ=None, cycle_id=cycle['cycle_id'])
    limits = contract.limits
    runtime_limits = RuntimeLimits(**{key: limits[key] for key in (
        'max_signal_rounds', 'max_signal_calls', 'max_llm_calls', 'max_tokens',
        'max_signals_per_round', 'max_llm_signals_per_round', 'finalization_token_reserve')},
        max_cost=limits['max_case_cost'])
    runner = StructuredLLMSignalRunner(caller)
    evaluator = RuntimePlanEvaluator(
        raw_info_store=store, evidence_resolver=resolver, controller=LLMResearchController(caller),
        signal_agent=LLMSignalRetrievalAgent(caller), predictor=LLMBlindPredictor(caller),
        prediction_root=root / 'predictions', trajectory_root=workspace.trajectory_root,
        limits=runtime_limits, llm_signal_runner=runner, signal_readiness_snapshot=initial,
        on_progress=emit,
    )
    meta = workspace.restore_meta()
    if bootstrap_entries:
        meta = PlanMetaMemory(maxlen=meta.maxlen, entries=bootstrap_entries + meta.entries)
    proposer = LLMInformationPlanProposer(caller, available_source_types=resolver.available_source_types)
    proposer.set_request_token_budget(runtime_limits.max_tokens)
    plan_engine = PlanEvolutionEngine(
        archive=workspace.restore_archive(expected_run_contract_hash=contract.contract_hash),
        meta_memory=meta, signal_registry=registry, evaluator=evaluator, proposer=proposer,
        critic=LLMPlanCritic(caller), round_reflector=LLMRoundReflector(caller), workspace=workspace,
        seed_plans=(default_information_plan(),), candidates_per_round=2,
        capability_source_types=resolver.available_source_types, evaluation_config=_evaluation(),
        case_readiness=evaluator.check_case_readiness, run_contract_hash=contract.contract_hash,
        parent_selection_seed=42, on_progress=emit,
    )
    mining = LLMSignalMiningModel(caller)
    mining.set_request_token_budget(runtime_limits.max_tokens)
    signal_engine = SignalEvolutionEngine(
        registry=registry, raw_info_store=store, discovery_cases=dataset.discovery,
        meta_memory=meta, workspace=workspace, mining_model=mining,
        update_model=LLMSignalUpdateModel(caller), llm_signal_runner=runner,
        identity_cases=(*dataset.discovery, *dataset.anchor, *dataset.evolution_validation),
        evidence_resolver=resolver, on_progress=emit, mining_heavy_action_limit=28,
        research_target_reveal=build_target_group_manifest(dataset.discovery, MAGNITUDE_GE3_CONTRACT),
        research_target_sampling=build_target_sampling_manifest(
            dataset.discovery, MAGNITUDE_GE3_CONTRACT, cycle_id=cycle['cycle_id'],
            base_seed=contract.contract_hash, dev_limit=4, check_limit=4),
    )
    result = DualLoopEvolutionEngine(
        plan_engine=plan_engine, signal_engine=signal_engine, signal_registry=registry,
        dataset=dataset, plan_rounds_per_signal_cycle=target_plan_rounds,
        cycle_mode=cycle_mode, on_progress=emit,
    ).run_cycle(cycle_id=cycle['cycle_id'], completed_plan_rounds=cycle['completed_plan_rounds'])
    slow = result.signal_evolution.to_dict()
    workspace.stage_slow_result(cycle_id=cycle['cycle_id'], result=slow)
    final = registry.freeze()
    workspace.complete_cycle(cycle_id=cycle['cycle_id'], observed_signal_registry_version=final.version,
                             observed_signal_registry_hash=final.registry_hash)
    atomic_write_json(root / 'acceptance_summary.json', {
        'contract_hash': contract.contract_hash,
        'plans': [{'plan_id': record.plan.plan_id, 'metrics': record.metrics.to_dict(),
                   'fitness': record.fitness.to_dict()} for record in plan_engine.archive.records],
        'slow': slow, 'last_completed_round': workspace.last_completed_round,
        'last_completed_cycle': workspace.last_completed_cycle,
        'content_inspection_status': 'pending_manual_artifact_review',
    })


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', required=True)
    parser.add_argument('--seed-registry', type=Path, help='Stable Registry directory to freeze into a new diagnostic workspace')
    parser.add_argument('--slow-bootstrap-from', type=Path, help='Reuse a committed Fast diagnostic range without rerunning its cases')
    parser.add_argument('--slow-history-from', type=Path, help='Continue a committed Slow publication in an ordinary Fast/Slow cycle')
    parser.add_argument('--reviewed-source-snapshot', type=Path, help='Explicit frozen reviewed store binding JSON for new inputs')
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument('--prepare-only', action='store_true')
    mode.add_argument('--run', action='store_true')
    args = parser.parse_args()
    root = Path(args.root).resolve()
    root.mkdir(parents=True, exist_ok=True)
    with EvolutionWorkspace.execution_lock_at(root):
        frozen = prepare(root, seed_registry=args.seed_registry, slow_bootstrap_from=args.slow_bootstrap_from,
                         slow_history_from=args.slow_history_from, reviewed_source_snapshot=args.reviewed_source_snapshot)
        print(f'Frozen diagnostic inputs: {canonical_json_hash(frozen)}', flush=True)
        if args.run:
            run(root, frozen)


if __name__ == '__main__':
    main()
