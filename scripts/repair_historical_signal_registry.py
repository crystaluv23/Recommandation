#!/usr/bin/env python3
"""Prepare and apply the user-approved exact historical Registry repair."""
from __future__ import annotations

import argparse
from contextlib import ExitStack, contextmanager
from dataclasses import asdict, replace
import hashlib
import json
from pathlib import Path
import re
import shutil
import socket
from types import SimpleNamespace
from unittest.mock import patch

from stock_opportunity_agent.artifacts import canonical_json_hash
from stock_opportunity_agent.cases.label_store import LabelStore
from stock_opportunity_agent.models import ValidationError
from stock_opportunity_agent.research.evolution_transport import ExternalAttemptLedger
from stock_opportunity_agent.research.local_role_exchange import _immutable
from stock_opportunity_agent.research.signal_evolution import SignalCandidateValidator, SignalEvolutionEngine
from stock_opportunity_agent.signal_capability_repair import _inventory, _source
from stock_opportunity_agent.signal_library import SignalRegistry, SignalSpec, signal_execution_behavior_identity

REPO = Path(__file__).resolve().parents[1]
BASE = REPO / 'runs/diagnostics/registry_capability_repair_20261025_v1'
ROOT = BASE / 'migration'
BASELINE = BASE / 'independent/baseline.json'
APPROVAL = REPO / 'runs/diagnostics/classification_fresh_consumer_20261024_v1/authorization-20261025.json'
POLICY = REPO / 'runs/diagnostics/financial_period_policy_20261023_v1/independent'
SPEC = REPO / 'spec/scripts/repair_historical_signal_registry.md'


def read(path):
    """Read saved JSON authority without model or source acquisition."""
    return json.loads(Path(path).read_bytes())


def binding(path):
    """Bind exact artifact bytes, including external approval evidence."""
    path = Path(path).resolve()
    return {'path': str(path), 'sha256': hashlib.sha256(path.read_bytes()).hexdigest()}


def code_bindings():
    """Freeze implementation before a prepared transition can mutate stable data."""
    return [binding(p) for p in sorted([*(REPO / 'src').rglob('*.py'), Path(__file__), SPEC])]


@contextmanager
def guards():
    """No network, labels, model dispatch or direct stable registration."""
    def forbidden(*args, **kwargs):
        raise ValidationError('repair driver forbids network/labels/models/direct registration')
    with ExitStack() as stack:
        for owner, name in ((socket, 'create_connection'), (socket.socket, 'connect'), (socket.socket, 'connect_ex'),
            (LabelStore, '__init__'), (LabelStore, 'load'), (LabelStore, 'ground_truth'), (LabelStore, 'record'),
            (ExternalAttemptLedger, 'reserve'), (SignalRegistry, 'register_stable')):
            stack.enter_context(patch.object(owner, name, forbidden))
        yield


def prepare_at(root: Path):
    """Prepare one byte-bound real-validation plan, without publishing it."""
    if root.exists():
        raise ValidationError('repair preparation destination must be new')
    baseline = read(BASELINE)
    approved_specs = read(POLICY / 'new-version-specs.json')['specs']
    approved_fixtures = read(POLICY / 'lineage-fixtures.json')['by_ref']
    if tuple(SignalSpec.from_dict(row).ref for row in approved_specs) != ('gross_margin_change:v4', 'revenue_acceleration:v3'):
        raise ValidationError('approved financial policy scope differs')
    authority = {'schema_version': 'signal-capability-repair-authority-v1',
        'approval': binding(APPROVAL), 'source_root': baseline['original_root'],
        'source_files': baseline['original_files'], 'input_version': baseline['registry_version'],
        'input_hash': baseline['registry_definition_hash'], 'input_refs': baseline['ordered_refs'],
        'disabled': baseline['audit']['disabled'], 'synthetic_fixture_cik': '0001999991',
        'approved_updates': {SignalSpec.from_dict(row).ref: {'spec': row,
            'tests': approved_fixtures[SignalSpec.from_dict(row).ref]} for row in approved_specs},
        'source_evidence': [binding(BASELINE), binding(POLICY / 'new-version-specs.json'),
            binding(POLICY / 'lineage-fixtures.json')]}
    original = _source(authority)
    root.mkdir(parents=True)
    _immutable(root / 'authority.json', authority)
    shutil.copytree(original.root, root / 'registry')
    registry = SignalRegistry(root / 'registry', candidate_root=root / 'candidates')
    validator = SignalCandidateValidator(original, llm_runner=None,
        forbidden_identity_terms=read(REPO / 'runs/diagnostics/gpre_native_initial_20261021_v1/stage/inputs.json')['sample']['identity']['identity_aliases'])
    policy = SimpleNamespace(validator=validator, _role_work_identity=SignalEvolutionEngine._role_work_identity)
    validator_hash = SignalEvolutionEngine._technical_validator_hash(policy)
    candidates, evaluations, admissions, validations = {}, {}, {}, {}
    descriptions, behaviors = set(), set()
    for prior_ref in authority['disabled']:
        prior = original.load_spec(prior_ref)
        candidate = replace(prior, version=prior.version + 1)
        ref = candidate.ref
        if ref in authority['approved_updates']:
            candidate = SignalSpec.from_dict(authority['approved_updates'][ref]['spec'])
            fixtures = authority['approved_updates'][ref]['tests']
        else:
            fixtures = json.loads(json.dumps(list(original.load_tests(prior_ref))))
            for fixture in fixtures:
                for document in fixture['documents']:
                    body = json.loads(document['content'])
                    body['cik'] = authority['synthetic_fixture_cik']
                    document['content'] = json.dumps(body, sort_keys=True, separators=(',', ':'))
                    document['metadata'] = {**document.get('metadata', {}), 'cik': authority['synthetic_fixture_cik']}
        registry.stage_candidate(candidate, skill=None, tests=fixtures, origin='user-approved-capability-repair')
        checked = validator.validate(candidate, skill=None, tests=fixtures)
        contract = {'accepted': checked.accepted, 'reasons': list(checked.reasons), 'executed_tests': checked.executed_tests}
        if not checked.accepted or checked.executed_tests != len(fixtures):
            _immutable(root / 'validation-failure.json', asdict(checked))
            raise ValidationError('full candidate validator rejected repair: ' + ref)
        description = ' '.join(re.findall(r'[a-z0-9]+', candidate.description.casefold()))
        behavior = signal_execution_behavior_identity(candidate, None)
        if description in descriptions or behavior in behaviors:
            raise ValidationError('repair batch semantic duplicate')
        descriptions.add(description); behaviors.add(behavior)
        digest = registry.candidate_hash(ref)
        record = {**asdict(checked), 'candidate_hash': digest, 'validator_hash': validator_hash,
            'input_registry_hash': authority['input_hash']}
        path = root / 'validation' / (ref + '.json')
        _immutable(path, record); validations[ref] = binding(path)
        prior_status = original.load_research_status(prior_ref)
        targets = prior_status.get('research_targets') or ['surge_direction']
        key = registry.record_candidate_admission(ref, input_registry_hash=authority['input_hash'],
            validator_hash=validator_hash, research_targets=targets, contract_validation=contract,
            research_provenance={'generation_case_ids': [], 'induction_case_ids': [], 'origin': 'unknown',
                'source_input_hash': canonical_json_hash(authority)})
        candidates[ref] = digest; evaluations[ref] = key
        admissions[ref] = binding(registry._candidate_spec_path(ref).parent / 'evaluations' / (key + '.json'))
    plan = {'schema_version': 'signal-capability-repair-plan-v1', 'authority': binding(root / 'authority.json'),
        'transition_id': 'approved-capability-repair-20261025', 'validated_candidates': candidates,
        'validated_evaluations': evaluations, 'admission_records': admissions, 'validation_records': validations,
        'validator_hash': validator_hash, 'code_files': code_bindings()}
    if _inventory(original.root) != authority['source_files'] or _inventory(registry.root) != authority['source_files']:
        raise ValidationError('original/clone changed during preparation')
    _immutable(root / 'plan.json', plan)
    _immutable(root / 'prepared.json', {'plan_hash': canonical_json_hash(plan), 'updates': len(candidates),
        'fixture_count': sum(read(row['path'])['executed_tests'] for row in validations.values()),
        'new_mining': 0, 'publication': 0, 'labels': 0, 'external_API': 0})
    return plan


def execute(root: Path, plan_hash: str):
    """Use the actual constrained transaction and verify exact applied replay."""
    plan = read(root / 'plan.json')
    if canonical_json_hash(plan) != plan_hash or read(root / 'prepared.json')['plan_hash'] != plan_hash:
        raise ValidationError('externally frozen repair plan hash differs')
    registry = SignalRegistry(root / 'registry', candidate_root=root / 'candidates')
    with guards():
        transition = registry.capability_repair(plan, plan_hash=plan_hash)
        snapshot = registry.freeze()
        replay = SignalRegistry(root / 'registry', candidate_root=root / 'candidates').capability_repair(plan, plan_hash=plan_hash)
        if transition != replay or len(snapshot.specs) != 18 or snapshot.version != 13:
            raise ValidationError('complete exact output/replay differs')
        if any(snapshot.research_status[ref]['effect_status'] != 'unverified' for ref in transition.promoted):
            raise ValidationError('repair inherited an effect claim')
    value = {'state': 'completed_pending_independent_review', 'plan_hash': plan_hash,
        'transition': asdict(transition), 'refs': [s.ref for s in snapshot.specs],
        'updates': 9, 'new_mining': 0, 'effect_status': 'unverified', 'original_unchanged': True,
        'business_pointer_advance': 0, 'labels': 0, 'external_API': 0}
    _immutable(root / 'result.json', value)
    return value


def main():
    """Use one fixed migration destination and explicit frozen-plan identity."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=('prepare', 'execute'))
    parser.add_argument('--plan-hash')
    args = parser.parse_args()
    with guards():
        if args.action == 'prepare':
            value = {'state': 'prepared', 'plan_hash': canonical_json_hash(prepare_at(ROOT))}
        else:
            value = execute(ROOT, args.plan_hash or '')
    print(json.dumps(value))


if __name__ == '__main__':
    main()
