"""Publish two approved updates through genuine local technical admission APIs."""
from contextlib import ExitStack
from dataclasses import asdict
import hashlib
import json
from pathlib import Path
import shutil
import socket
import ssl
import sys
from types import SimpleNamespace
from unittest.mock import patch

from stock_opportunity_agent.artifacts import canonical_json_hash
from stock_opportunity_agent.cases.label_store import LabelStore
from stock_opportunity_agent.data.raw_info import RawInfoStore
from stock_opportunity_agent.research.evolution_transport import ExternalAttemptLedger
from stock_opportunity_agent.research.signal_evolution import (
    SignalCandidateValidator, SignalEvolutionEngine, _normalize_semantics,
)
from stock_opportunity_agent.signal_library import SignalRegistry, SignalSpec

BASE = Path(__file__).resolve().parent
REPO = BASE.parents[2]
PREVIOUS = REPO / 'runs/diagnostics/financial_period_policy_20261023_v1'
OUT = BASE / 'publication'
OWN = REPO / 'spec/scripts/publish_approved_financial_versions.md'
TRANSITION = 'approved-financial-period-20261024'
REFS = ('gross_margin_change:v4', 'revenue_acceleration:v3')


def read(path):
    return json.loads(Path(path).read_bytes())


def bind(path):
    p = Path(path).resolve()
    return {'path': str(p), 'sha256': hashlib.sha256(p.read_bytes()).hexdigest()}


def files(root):
    return [bind(p) for p in sorted(Path(root).rglob('*')) if p.is_file()]


def check(rows):
    for row in rows:
        if bind(row['path']) != row:
            raise ValueError('frozen input changed: ' + row['path'])


def save(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('x') as stream:
        json.dump(value, stream, indent=2, ensure_ascii=False)
        stream.write('\n')


def prepare():
    if OUT.exists():
        raise ValueError('publication preparation is single-entry')
    previous = read(PREVIOUS / 'native-approved/plan.json')
    old_plan = read(REPO / 'runs/diagnostics/current_financial_apply_20261021_v1/native/stage/plan.json')
    authority = old_plan['group']
    candidate_input = read(PREVIOUS / 'independent/new-version-specs.json')
    specs = candidate_input['specs']
    if tuple(SignalSpec.from_dict(s).ref for s in specs) != REFS:
        raise ValueError('approved exact two-version scope differs')
    source_rows = files(authority['root'])
    evidence = [bind(PREVIOUS / name) for name in (
        'independent/new-version-specs.json', 'independent/lineage-fixtures.json',
        'independent/candidate-final-lineage-review-report.json',
        'independent/actual-review.json', 'independent/source-only-lineage-addendum.json',
        'native-approved/plan.json', 'native-approved/native-batch.json')]
    code = [*files(REPO / 'src'), bind(__file__), bind(OWN)]
    code = [row for row in code if row['path'].endswith('.py') or row['path'] == str(OWN)]
    for rel, digest in candidate_input['code_bindings'].items():
        if bind(REPO / rel)['sha256'] != digest:
            raise ValueError('reviewed implementation changed')
    OUT.mkdir(parents=True)
    shutil.copytree(authority['root'], OUT / 'registry')
    registry = SignalRegistry(OUT / 'registry', candidate_root=OUT / 'candidates')
    snapshot = registry.freeze()
    if (snapshot.version != authority['version'] or snapshot.registry_hash != authority['registry_hash']
            or [s.ref for s in snapshot.specs] != authority['refs']):
        raise ValueError('complete cloned v12/18 Registry differs')
    aliases = read(REPO / 'runs/diagnostics/gpre_native_initial_20261021_v1/stage/inputs.json')['sample']['identity']['identity_aliases']
    plan = dict(schema_version='approved-financial-publication-v1', authority=authority,
        specs=specs, fixture_input=read(PREVIOUS / 'independent/lineage-fixtures.json'),
        source_rows=source_rows, evidence=evidence, code=code,
        clone_before=files(OUT / 'registry'), forbidden_identity_terms=aliases,
        research_provenance={'generation_case_ids': ['cik_0001309402:20250530'],
            'induction_case_ids': ['cik_0001309402:20250530'], 'origin': 'unknown',
            'source_input_hash': previous['plan_hash']},
        fixed_updates=2, new_mining=0, fresh_role_calls=0, external_API=0,
        labels=0, real_source_reexecution=0, business_pointer_advance=0)
    plan['plan_hash'] = canonical_json_hash(plan)
    save(OUT / 'plan.json', plan)
    print(plan['plan_hash'])


def forbidden(*args, **kwargs):
    raise RuntimeError('publication diagnostic forbids network/models/labels/direct registration')


def execute(expected_hash):
    p = read(OUT / 'plan.json')
    if canonical_json_hash({k: v for k, v in p.items() if k != 'plan_hash'}) != expected_hash or p['plan_hash'] != expected_hash:
        raise ValueError('exact prepared plan hash required')
    check(p['source_rows'] + p['evidence'] + p['code'] + p['clone_before'])
    if any((OUT / name).exists() for name in ('execution-start.json', 'result.json', 'failure.json')):
        raise ValueError('terminal publication attempt cannot reenter')
    save(OUT / 'execution-start.json', {'plan_hash': expected_hash})
    try:
        with ExitStack() as stack:
            for owner, name in ((socket, 'socket'), (socket, 'create_connection'),
                    (LabelStore, '__init__'), (LabelStore, 'load'), (LabelStore, 'ground_truth'),
                    (LabelStore, 'record'), (ExternalAttemptLedger, 'reserve'),
                    (SignalRegistry, 'register_stable')):
                stack.enter_context(patch.object(owner, name, forbidden))
            registry = SignalRegistry(OUT / 'registry', candidate_root=OUT / 'candidates')
            snapshot = registry.freeze()
            validator = SignalCandidateValidator(registry, llm_runner=None,
                forbidden_identity_terms=p['forbidden_identity_terms'])
            # Reuse the owning pure policy calculation; no engine/cycle is fabricated.
            policy = SimpleNamespace(validator=validator,
                _role_work_identity=SignalEvolutionEngine._role_work_identity)
            validator_hash = SignalEvolutionEngine._technical_validator_hash(policy)
            candidates, evaluations, decisions = {}, {}, []
            semantic_seen, behavior_seen = set(), set()
            for raw in p['specs']:
                spec = SignalSpec.from_dict(raw)
                fixtures = p['fixture_input']['by_ref'][spec.ref]
                registry.stage_candidate(spec, tests=fixtures, origin='user-approved-period-policy-update')
                checked = validator.validate(spec, skill=None, tests=fixtures)
                semantic = _normalize_semantics(spec.description)
                behavior = validator._behavior_identity(spec, None)
                if semantic in semantic_seen or behavior in behavior_seen:
                    raise ValueError('semantic duplicate in approved update batch')
                decision = {**asdict(checked), 'candidate_hash': registry.candidate_hash(spec.ref)}
                decisions.append(decision)
                save(OUT / 'validation' / (spec.ref + '.json'), decision)
                if not checked.accepted or checked.executed_tests != len(fixtures):
                    raise ValueError('technical validator rejected approved candidate')
                stable = next(s for s in snapshot.specs if s.signal_id == spec.signal_id)
                targets = snapshot.research_status.get(stable.ref, {}).get('research_targets') or ('surge_direction',)
                key = registry.record_candidate_admission(spec.ref,
                    input_registry_hash=snapshot.registry_hash, validator_hash=validator_hash,
                    research_targets=targets, contract_validation={
                        'accepted': checked.accepted, 'reasons': list(checked.reasons),
                        'executed_tests': checked.executed_tests},
                    research_provenance=p['research_provenance'])
                candidates[spec.ref] = registry.candidate_hash(spec.ref)
                evaluations[spec.ref] = key
                semantic_seen.add(semantic); behavior_seen.add(behavior)
            arguments = dict(validated_candidates=candidates, validated_evaluations=evaluations,
                transition_id=TRANSITION, input_version=snapshot.version,
                input_hash=snapshot.registry_hash, input_refs=tuple(s.ref for s in snapshot.specs))
            transition = registry.promote_validated_batch(**arguments)
            save(OUT / 'transition.json', asdict(transition))
            reopened = SignalRegistry(OUT / 'registry', candidate_root=OUT / 'candidates')
            output = reopened.freeze()
            old = reopened.snapshot_from_refs(p['authority']['version'], tuple(p['authority']['refs']))
            if old.registry_hash != snapshot.registry_hash:
                raise ValueError('old exact Registry snapshot no longer reconstructs')
            for raw in p['specs']:
                spec = SignalSpec.from_dict(raw)
                if reopened.load_spec(spec.ref).to_dict() != raw:
                    raise ValueError('published definition differs')
                status = output.research_status[spec.ref]
                if status['effect_status'] != 'unverified':
                    raise ValueError('publication claimed an effect')
            replay = reopened.promote_validated_batch(**arguments)
            if asdict(replay) != asdict(transition) or reopened.version != snapshot.version + 1:
                raise ValueError('atomic transition replay was not idempotent')
            save(OUT / 'output-snapshot.json', {'version': output.version,
                'registry_hash': output.registry_hash, 'learning_hash': output.learning_hash,
                'refs': [s.ref for s in output.specs],
                'research_status': {k: dict(v) for k, v in output.research_status.items()},
                'cards': [c.to_dict() for c in reopened.list_signal_cards()]})
        check(p['source_rows'] + p['evidence'] + p['code'])
        result = dict(status='completed_pending_independent_review', plan_hash=expected_hash,
            input_version=snapshot.version, output_version=output.version,
            updates=2, new_mining=0, fixtures=sum(d['executed_tests'] for d in decisions),
            published=list(transition.promoted), effect='unverified', fresh_role_calls=0,
            original_registry_unchanged=True, labels=0, network=0, business_pointer_advance=0)
        save(OUT / 'result.json', result)
        save(OUT / 'completed-files.json', files(OUT))
        print(json.dumps(result))
    except Exception as error:
        save(OUT / 'failure.json', {'type': type(error).__name__, 'error': str(error)})
        raise


if __name__ == '__main__':
    if sys.argv[1:] == ['prepare']:
        prepare()
    elif len(sys.argv) == 3 and sys.argv[1] == 'execute':
        execute(sys.argv[2])
    else:
        raise SystemExit('prepare | execute EXACT_PLAN_HASH')
