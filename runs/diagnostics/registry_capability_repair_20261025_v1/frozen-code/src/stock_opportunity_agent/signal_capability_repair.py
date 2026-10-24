"""Exact, approved issuer-fixture recovery for an unhealthy Signal Registry."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import re
from typing import Any, Mapping

from stock_opportunity_agent.models import ValidationError
from stock_opportunity_agent.signal_library import (
    SignalExecutionType, SignalRegistry, SignalRegistryTransition, SignalSpec, SignalStats,
    _canonical_hash, _read_json, _validate_id, _write_or_verify_json,
    signal_execution_behavior_identity, signal_version_content_hash,
)


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise ValidationError("capability repair: " + message)


def _checked_path(row: Mapping[str, str]) -> Path:
    path = Path(row['path'])
    _require(path.is_file() and not path.is_symlink(), 'bound artifact missing or symlink')
    _require(hashlib.sha256(path.read_bytes()).hexdigest() == row['sha256'], 'bound artifact changed')
    return path


def _bound(row: Mapping[str, str]) -> dict[str, Any]:
    return _read_json(_checked_path(row))


def _intent_matches(stored: Mapping[str, Any], intent: Mapping[str, Any]) -> bool:
    return set(intent).issubset(stored) and _canonical_hash(
        {key: stored[key] for key in intent}) == _canonical_hash(dict(intent))


def _inventory(root: Path) -> dict[str, str]:
    rows = {}
    for path in root.rglob('*'):
        _require(not path.is_symlink(), 'Registry symlink is forbidden')
        if path.is_file():
            rows[path.relative_to(root).as_posix()] = hashlib.sha256(path.read_bytes()).hexdigest()
    return rows


def _source(authority: Mapping[str, Any]) -> SignalRegistry:
    """Read the exact original without constructor/candidate-directory writes."""
    root = Path(authority['source_root']).resolve()
    for row in authority.get('source_evidence', ()):
        _checked_path(row)
    _require(_inventory(root) == authority['source_files'], 'original byte inventory changed')
    original = object.__new__(SignalRegistry)
    original.root = root
    original.knowledge_workspace_root = root.parent
    original.candidate_root = root.parent / 'unused_repair_readonly_candidates'
    original._transition_recovery_active = False
    original._fault_injector = None
    refs = tuple(authority['input_refs'])
    _require(original.version == authority['input_version'], 'original version changed')
    _require(tuple(card.ref for card in original.list_signal_cards()) == refs, 'original complete membership changed')
    _require(original.snapshot_from_refs(original.version, refs).registry_hash == authority['input_hash'], 'original definition hash changed')
    disabled = {ref: list(reasons) for ref, reasons in original.audit_capabilities().disabled.items()}
    _require(bool(disabled) and disabled == authority['disabled'], 'original disabled reasons differ')
    _require(all(len(reasons) == 1 and reasons[0].endswith(
        'SEC Company Facts opaque company has no explicit issuer binding') for reasons in disabled.values()),
        'failure family is outside issuer-fixture repair')
    return original


def _identity_only_fixture(new: Mapping[str, Any], old: Mapping[str, Any], cik: str) -> None:
    _require(len(new.get('documents', ())) == len(old.get('documents', ())), 'fixture documents changed')
    cleaned = json.loads(json.dumps(dict(new)))
    for item, prior in zip(cleaned['documents'], old['documents']):
        body, old_body = json.loads(item['content']), json.loads(prior['content'])
        _require(body.pop('cik', None) == cik, 'new fixture body must declare synthetic CIK')
        _require(item.get('metadata', {}).pop('cik', None) == cik, 'new fixture metadata must declare same CIK')
        _require(_canonical_hash(body) == _canonical_hash(old_body), 'fixture body changed beyond CIK')
        item['content'] = prior['content']
        if 'metadata' not in prior and not item['metadata']:
            item.pop('metadata')
    _require(_canonical_hash(cleaned) == _canonical_hash(dict(old)), 'fixture changed beyond issuer declaration')


def _candidates(registry: SignalRegistry, original: SignalRegistry,
                authority: Mapping[str, Any], plan: Mapping[str, Any]) -> dict[str, SignalSpec]:
    old_by_id = {spec.signal_id: spec for spec in original.snapshot_from_refs(
        authority['input_version'], tuple(authority['input_refs'])).specs}
    expected = {f"{old_by_id[ref.rsplit(':v', 1)[0]].signal_id}:v{old_by_id[ref.rsplit(':v', 1)[0]].version + 1}"
        for ref in authority['disabled']}
    candidates = plan['validated_candidates']
    _require(set(candidates) == expected, 'must repair exactly every disabled next version')
    _require(set(plan['validated_evaluations']) == expected and set(plan['admission_records']) == expected
        and set(plan['validation_records']) == expected, 'every candidate needs exact admission and validation')
    approved = authority['approved_updates']
    _require(set(approved).issubset(expected), 'approved definition change outside disabled updates')
    stable = {key: (" ".join(re.findall(r'[a-z0-9]+', spec.description.casefold())),
        signal_execution_behavior_identity(spec, original.load_skill(spec.ref))) for key, spec in old_by_id.items()}
    seen_descriptions, seen_behaviors, output = set(), set(), {}
    for ref, digest in sorted(candidates.items()):
        spec, skill = registry.load_candidate(ref)
        prior = old_by_id.get(spec.signal_id)
        _require(prior is not None and spec.version == prior.version + 1 and spec.category == prior.category,
            'next version/category/identity changed')
        _require(spec.execution_type is SignalExecutionType.DETERMINISTIC and skill is None,
            'issuer-fixture repair supports deterministic definitions only')
        _require(registry.candidate_hash(ref) == digest, 'candidate content hash changed')
        fixtures = registry.load_candidate_tests(ref)
        _require(bool(fixtures), 'nonempty complete fixtures required')
        if ref in approved:
            _require(_canonical_hash(spec.to_dict()) == _canonical_hash(approved[ref]['spec'])
                and _canonical_hash(list(fixtures)) == _canonical_hash(approved[ref]['tests']),
                'approved definition or fixtures differ')
        else:
            expected_spec = {**prior.to_dict(), 'version': spec.version}
            _require(_canonical_hash(spec.to_dict()) == _canonical_hash(expected_spec)
                and skill == original.load_skill(prior.ref), 'unapproved definition/skill drift')
            old_tests = original.load_tests(prior.ref)
            _require(len(fixtures) == len(old_tests), 'identity-only fixture count changed')
            for fixture, old_fixture in zip(fixtures, old_tests):
                _identity_only_fixture(fixture, old_fixture, authority['synthetic_fixture_cik'])
        description = " ".join(re.findall(r'[a-z0-9]+', spec.description.casefold()))
        behavior = signal_execution_behavior_identity(spec, skill)
        _require(description not in seen_descriptions and behavior not in seen_behaviors,
            'duplicate description or behavior in repair batch')
        _require(all(description != d and behavior != b for key, (d, b) in stable.items() if key != spec.signal_id),
            'duplicate description or behavior of another stable Signal')
        seen_descriptions.add(description); seen_behaviors.add(behavior)
        key = plan['validated_evaluations'][ref]
        record = registry.load_candidate_validation(ref, evaluation_key=key)
        _require(record is not None and record.get('schema_version') == 'signal-candidate-admission-v1',
            'exact admission-v1 required')
        bound_admission = _bound(plan['admission_records'][ref])
        _require(_canonical_hash(record) == _canonical_hash(bound_admission), 'admission record changed')
        identity = record['admission_identity']
        _require(identity['input_registry_hash'] == authority['input_hash'] and
            identity['validator_hash'] == plan['validator_hash'], 'admission validator/input identity differs')
        validation = _bound(plan['validation_records'][ref])
        contract = {field: validation[field] for field in ('accepted', 'reasons', 'executed_tests')}
        _require(validation['signal_ref'] == ref and validation['candidate_hash'] == digest
            and validation['validator_hash'] == plan['validator_hash']
            and validation['input_registry_hash'] == authority['input_hash']
            and contract == record['contract_validation'] and contract['accepted'] is True
            and contract['reasons'] == [] and type(contract['executed_tests']) is int
            and contract['executed_tests'] == len(fixtures), 'complete actual validation binding differs')
        output[ref] = spec
    return output


def _successor_files(registry: SignalRegistry, original: SignalRegistry,
                     authority: Mapping[str, Any], plan: Mapping[str, Any], *, prepared: bool) -> None:
    current = _inventory(registry.root)
    baseline = authority['source_files']
    _require(set(baseline).issubset(current), 'original successor file removed')
    if not prepared:
        _require(current == baseline, 'successor is not exact original byte clone')
        return
    allowed_json = {'registry.json': [{'version': authority['input_version']}, {'version': authority['input_version'] + 1}]}
    for ref in plan['validated_candidates']:
        spec, skill = registry.load_candidate(ref)
        prefix = f'{spec.category}/{spec.signal_id}'
        path = prefix + '/manifest.json'
        old = _read_json(original.root / path)
        advanced = {**old, 'stable_version': spec.version}
        admitted = {**advanced, 'admission_keys': {**old.get('admission_keys', {}),
            str(spec.version): plan['validated_evaluations'][ref]}}
        allowed_json[path] = [old, advanced, admitted]
        version = prefix + f'/versions/v{spec.version}/'
        allowed_json[version + 'spec.json'] = [spec.to_dict()]
        allowed_json[version + 'tests.json'] = [{'tests': list(registry.load_candidate_tests(ref))}]
        allowed_json[version + 'admission.json'] = [_bound(plan['admission_records'][ref])]
        if prefix + '/stats.json' not in baseline:
            allowed_json[prefix + '/stats.json'] = [SignalStats().to_dict()]
    transition = '.transitions/' + plan['transition_id'] + '.json'
    for path, digest in current.items():
        if path == transition:
            continue  # Exact transition identity/status is checked before recovery.
        if path in allowed_json:
            actual = _canonical_hash(_read_json(registry.root / path))
            _require(any(actual == _canonical_hash(row) for row in allowed_json[path]), 'unexpected partial output content: ' + path)
        else:
            _require(path in baseline and digest == baseline[path], 'historical/extra successor file changed: ' + path)


def verify_applied_repair_readable(registry: SignalRegistry, path: Path,
                                  stored: Mapping[str, Any]) -> None:
    """Validate committed local definitions without recursive reads or old source access."""
    try:
        plan = stored['repair_plan']
        current_version = _read_json(registry._registry_path)['version']
        version = stored['output_registry_version']
        _require(type(current_version) is int and type(stored['input_registry_version']) is int
            and type(version) is int and version == stored['input_registry_version'] + 1
            and current_version >= version, 'uncommitted applied repair version')
        _require(stored['repair_plan_hash'] == _canonical_hash(plan)
            and plan['schema_version'] == 'signal-capability-repair-plan-v1', 'applied repair plan hash differs')
        promoted = sorted(plan['validated_candidates'])
        expected_record = {'schema_version': 'signal-registry-capability-repair-v1', 'mode': 'capability_repair',
            'transition_id': path.stem, 'input_registry_version': stored['input_registry_version'],
            'input_registry_hash': stored['input_registry_hash'], 'input_signal_refs': stored['input_signal_refs'],
            'validated_candidates': plan['validated_candidates'], 'validated_evaluations': plan['validated_evaluations'],
            'repair_plan_hash': stored['repair_plan_hash'], 'repair_plan': plan, 'status': 'applied',
            'output_registry_version': version, 'output_registry_hash': stored['output_registry_hash'],
            'promoted': promoted}
        _require(_canonical_hash(stored) == _canonical_hash(expected_record), 'applied repair record incomplete or changed')
        expected_refs = {ref.rsplit(':v', 1)[0]: ref for ref in stored['input_signal_refs']}
        _require(len(expected_refs) == len(stored['input_signal_refs'])
            and set(plan['validated_evaluations']) == set(promoted)
            and all(ref.rsplit(':v', 1)[0] in expected_refs for ref in promoted), 'applied repair membership invalid')
        expected_refs.update({ref.rsplit(':v', 1)[0]: ref for ref in promoted})
        specs, skills, latest_refs = [], {}, {}
        for manifest_path in sorted(registry.root.glob('*/*/manifest.json')):
            manifest = _read_json(manifest_path)
            _require(type(manifest['stable_version']) is int, 'applied manifest version type differs')
            signal_id = manifest['signal_id']
            latest_refs[signal_id] = f"{signal_id}:v{manifest['stable_version']}"
            if signal_id not in expected_refs:
                continue
            historical_version = int(expected_refs[signal_id].rsplit(':v', 1)[1])
            _require(manifest['stable_version'] >= historical_version, 'applied historical version regressed')
            folder = manifest_path.parent / 'versions' / f'v{historical_version}'
            raw_spec = _read_json(folder / 'spec.json')
            _require(type(raw_spec['version']) is int, 'applied definition version type differs')
            spec = SignalSpec.from_dict(raw_spec)
            _require(spec.signal_id == manifest['signal_id'] and spec.category == manifest['category']
                and spec.version == historical_version
                and spec.category == manifest_path.parent.parent.name
                and spec.signal_id == manifest_path.parent.name, 'applied path/definition identity differs')
            specs.append(spec)
            if spec.execution_type is SignalExecutionType.LLM:
                skills[spec.ref] = (folder / 'skill.md').read_text(encoding='utf-8')
            if spec.ref in plan['validated_candidates']:
                admission_path = folder / 'admission.json'
                _require(hashlib.sha256(admission_path.read_bytes()).hexdigest()
                    == plan['admission_records'][spec.ref]['sha256'], 'applied local admission bytes differ')
                admission = _read_json(admission_path)
                _require(admission['admission_identity']['input_registry_hash'] == stored['input_registry_hash']
                    and admission['candidate_hash'] == plan['validated_candidates'][spec.ref]
                    and admission['evaluation_key'] == plan['validated_evaluations'][spec.ref]
                    and manifest.get('admission_keys', {}).get(str(spec.version)) == admission['evaluation_key'],
                    'applied local admission lineage differs')
                historical_hash = signal_version_content_hash(spec, skills.get(spec.ref),
                    _read_json(folder / 'tests.json')['tests'])
                _require(historical_hash == plan['validated_candidates'][spec.ref],
                    'applied historical version content differs from admission')
        actual_refs = {spec.signal_id: spec.ref for spec in specs}
        _require(len(specs) == len(actual_refs) and actual_refs == expected_refs, 'applied complete membership differs')
        _require(current_version != version or latest_refs == expected_refs,
            'latest membership differs before a successor version')
        payload = json.dumps({'version': version, 'specs': [spec.to_dict() for spec in specs], 'skills': skills},
            sort_keys=True, separators=(',', ':'))
        _require(hashlib.sha256(payload.encode('utf-8')).hexdigest() == stored['output_registry_hash'],
            'applied local definition hash differs')
    except (KeyError, TypeError, ValueError, OSError) as error:
        raise ValidationError('capability repair: invalid applied commit record requires recovery') from error


def verify_repair_output(registry: SignalRegistry, intent: Mapping[str, Any]) -> None:
    """Audit complete output membership and bytes before version publication."""
    plan = intent['repair_plan']; authority = _bound(plan['authority'])
    stored = _read_json(registry.root / '.transitions' / (plan['transition_id'] + '.json'))
    _require(_intent_matches(stored, intent)
        and stored.get('status') in {'prepared', 'applied'}, 'transition changed during materialization')
    original = _source(authority)
    _successor_files(registry, original, authority, plan, prepared=True)
    expected = {spec.signal_id: spec.ref for spec in original.snapshot_from_refs(
        authority['input_version'], tuple(authority['input_refs'])).specs}
    expected.update({ref.rsplit(':v', 1)[0]: ref for ref in plan['validated_candidates']})
    actual = {card.signal_id: card.ref for card in registry.list_signal_cards()}
    _require(actual == expected, 'complete output membership differs')
    _require(not registry.audit_capabilities().disabled, 'complete output capability audit failed')
    _require(all(registry.load_research_status(ref)['effect_status'] == 'unverified'
        for ref in plan['validated_candidates']), 'repaired versions must start effect-unverified')


def apply_capability_repair(registry: SignalRegistry, plan: Mapping[str, Any], *, plan_hash: str):
    """Apply or recover one immutable approved plan; never authorize a new scope."""
    _require(_canonical_hash(dict(plan)) == plan_hash and
        plan.get('schema_version') == 'signal-capability-repair-plan-v1', 'plan identity invalid')
    authority = _bound(plan['authority'])
    _require(authority.get('schema_version') == 'signal-capability-repair-authority-v1', 'authority schema invalid')
    approval = _bound(authority['approval'])
    _require(approval.get('approved') is True and approval.get('registry_capability_repair_approved') is True,
        'explicit repair approval required')
    _checked_path(approval['proposal'])
    required_code = {Path(__file__).resolve(), Path(__file__).with_name('signal_library.py').resolve(),
        Path(__file__).parent.joinpath('research/signal_evolution.py').resolve()}
    _require(required_code.issubset({Path(row['path']).resolve() for row in plan['code_files']}),
        'complete repair/validator/executor code bindings required')
    for row in plan['code_files']:
        path = Path(row['path'])
        _require(path.is_file() and hashlib.sha256(path.read_bytes()).hexdigest() == row['sha256'], 'frozen implementation changed')
    original = _source(authority)
    source, target = original.root.resolve(), registry.root.resolve()
    _require(source != target and not target.is_relative_to(source) and not source.is_relative_to(target)
        and not registry.candidate_root.resolve().is_relative_to(source), 'original/successor/candidate roots must be separate')
    _inventory(registry.candidate_root)  # Reject candidate symlink trees before any marker write.
    transition_id = plan['transition_id']; _validate_id(transition_id, 'Signal transition id')
    transition_path = registry.root / '.transitions' / (transition_id + '.json')
    for path in (registry.root / '.transitions').glob('*.json'):
        if path != transition_path:
            _require(_read_json(path).get('status') == 'applied', 'unrelated or unknown transition blocks repair')
    intent = {'schema_version': 'signal-registry-capability-repair-v1', 'mode': 'capability_repair',
        'transition_id': transition_id, 'input_registry_version': authority['input_version'],
        'input_registry_hash': authority['input_hash'], 'input_signal_refs': authority['input_refs'],
        'validated_candidates': plan['validated_candidates'], 'validated_evaluations': plan['validated_evaluations'],
        'repair_plan_hash': plan_hash, 'repair_plan': dict(plan)}
    prepared = transition_path.exists()
    if prepared:
        stored = _read_json(transition_path)
        _require(_intent_matches(stored, intent) and stored.get('status') in {'prepared', 'applied'},
            'transition replay identity/status mismatch')
    else:
        registry._assert_registry_readable()
    registry._transition_recovery_active = prepared
    try:
        _require(registry.version in ({authority['input_version'], authority['input_version'] + 1}
            if prepared else {authority['input_version']}), 'successor version differs')
        _successor_files(registry, original, authority, plan, prepared=prepared)
        _candidates(registry, original, authority, plan)
        candidates = tuple(sorted(plan['validated_candidates'].items()))
        registry._validate_promotion_candidates(candidates, input_refs=tuple(authority['input_refs']),
            input_hash=authority['input_hash'], validated_evaluations=plan['validated_evaluations'])
        if prepared and stored['status'] == 'applied':
            verify_repair_output(registry, intent)
            output = registry.freeze()
            expected_applied = {**intent, 'status': 'applied', 'output_registry_version': output.version,
                'output_registry_hash': output.registry_hash, 'promoted': list(sorted(plan['validated_candidates']))}
            _require(output.version == authority['input_version'] + 1
                and _canonical_hash(stored) == _canonical_hash(expected_applied), 'applied output identity differs')
            for ref in plan['validated_candidates']:
                marker = registry._candidate_spec_path(ref).parent / 'promotion.json'
                expected = {'promoted': True, 'mode': 'capability_repair', 'transition_id': transition_id,
                    'evaluation_key': plan['validated_evaluations'][ref],
                    'output_registry_version': output.version, 'output_registry_hash': output.registry_hash}
                _require(marker.is_file() and _canonical_hash(_read_json(marker)) == _canonical_hash(expected),
                    'applied promotion marker missing or changed')
            return SignalRegistryTransition(transition_id, authority['input_version'], authority['input_hash'],
                output.version, output.registry_hash, tuple(sorted(plan['validated_candidates'])))
        if not prepared:
            _write_or_verify_json(transition_path, {**intent, 'status': 'prepared'})
            registry._fault_checkpoint('after_transition_prepared')
        registry._transition_recovery_active = True
        result = registry._apply_prepared_transition(transition_path=transition_path, intent=intent,
            transition_id=transition_id, input_version=authority['input_version'], input_hash=authority['input_hash'],
            input_refs=tuple(authority['input_refs']), ordered_candidates=candidates,
            validated_evaluations=plan['validated_evaluations'])
        _require(_inventory(source) == authority['source_files'], 'original changed after application')
        return result
    finally:
        registry._transition_recovery_active = False
