"""Freeze a new prospective ICFR oracle without modifying prior semantics or files."""
from __future__ import annotations
import copy
import datetime
import difflib
import hashlib
import json
from pathlib import Path
import tarfile

ROOT = Path('/Users/l/Project/Recommandation')
BASE = ROOT / 'runs/diagnostics/icfr_native_capability_20261023_v1'
OUT = BASE / 'oracle-v2'
OLD = BASE / 'oracle/acceptance-obligations.json'
STOP = BASE / 'parent-control-stop.json'
STAGE_SPEC = ROOT / 'spec/scripts/run_icfr_native_capability_stage.md'
MINING_SPEC = ROOT / 'spec/src/stock_opportunity_agent/research/signal_mining_agent.md'


def sha(raw: bytes) -> str:
    """Hash exact bytes as a binding, never as semantic evidence by itself."""
    return hashlib.sha256(raw).hexdigest()


def bind(path: Path) -> dict:
    """Bind the exact existing local file."""
    return {'path': str(path), 'sha256': sha(path.read_bytes())}


def canonical(value) -> bytes:
    """Serialize protected semantics deterministically for an equality check."""
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':')).encode()


def main() -> None:
    """Copy original obligations, changing only prospective metadata and bindings."""
    dest = OUT / 'acceptance-obligations.json'
    if dest.exists():
        raise RuntimeError('New oracle already frozen; refusing overwrite')
    assert not (BASE / 'stage-v2').exists(), 'New actor stage must not exist before this freeze'
    old_bytes = OLD.read_bytes()
    old = json.loads(old_bytes)
    assert old['freeze_revision'] == 2
    stop = json.loads(STOP.read_bytes())
    archive = Path(stop['runtime_archive']['path'])
    archive_binding = bind(archive)
    assert archive_binding['sha256'] == stop['runtime_archive']['sha256']
    assert stop['native_stage_status'] == 'pending_independent_role'
    assert stop['answered_unique_requests'] == 12 and stop['logical_reservations'] == 2001316
    assert stop['pending_not_dispatched'] and not stop['budget_exhaustion']
    assert stop['candidate_denominator'] == 1 and stop['consumer_denominator'] == 4
    assert stop['candidate_passed'] == 0 and stop['consumer_attempted'] == 0
    # Read old persisted state only as opaque file bytes to verify the stop mapping.
    # No author response/candidate body is parsed or used to change obligations.
    mapped = stop['stage_files_at_stop']
    stage = Path(stop['stage_path'])
    mismatches = []
    for relative, expected in mapped.items():
        p = stage / relative
        if not p.is_file() or sha(p.read_bytes()) != expected:
            mismatches.append(relative)
    assert not mismatches, mismatches
    with tarfile.open(archive) as retained:
        old_stage_spec = retained.extractfile(str(STAGE_SPEC.relative_to(ROOT))).read().decode()
        old_mining_spec = retained.extractfile(str(MINING_SPEC.relative_to(ROOT))).read().decode()
    stage_diff = ''.join(difflib.unified_diff(old_stage_spec.splitlines(True), STAGE_SPEC.read_text().splitlines(True),
                                             fromfile='frozen-runtime/stage-spec', tofile='current/stage-spec'))
    mining_diff = ''.join(difflib.unified_diff(old_mining_spec.splitlines(True), MINING_SPEC.read_text().splitlines(True),
                                              fromfile='frozen-runtime/mining-spec', tofile='current/mining-spec'))
    assert '## Resources and real roles' in old_stage_spec
    assert (old_stage_spec.split('## Resources and real roles', 1)[1]
            == STAGE_SPEC.read_text().split('## Resources and real roles', 1)[1]), 'Resource/native-phase text drift'
    new = copy.deepcopy(old)
    new['frozen_at_utc'] = datetime.datetime.now(datetime.timezone.utc).isoformat()
    new['freeze_revision'] = 3
    new['contract_bindings'] = [bind(Path(b['path'])) for b in old['contract_bindings']]
    new['contract_bindings'].append(bind(MINING_SPEC))
    new['predecessor_bindings'] = [bind(STOP), archive_binding]
    new['prospective_revision'] = {
        'evaluation_destination': str(BASE / 'stage-v2'),
        'oracle_destination': str(dest),
        'source_oracle': bind(OLD),
        'new_actor_stage_existed_at_freeze': False,
        'new_candidate_or_consumer_outputs_read': False,
        'old_author_content_parsed': False,
        'purpose': 'New code-version evaluation after diagnosed narrative working-view body loss. Same source population, semantic obligations, scope and budget ceilings; no old cache/author answer reuse.',
        'old_stage_disposition': {k: stop[k] for k in [
            'native_stage_status', 'native_completion_exists', 'pending_unanswered_request_hash',
            'pending_not_dispatched', 'answered_unique_requests', 'logical_reservations', 'logical_unit',
            'host_tokens_and_cost', 'candidate_denominator', 'candidate_passed', 'candidate_acceptance',
            'consumer_denominator', 'consumer_attempted', 'budget_exhaustion', 'business_commit']},
        'old_denominators_not_rewritten': True,
        'new_fixed_denominators_are_independent': True,
        'driver_obligation': 'Before prepare/verify, independently verify predecessor stop stage-file mapping and frozen archive, original unanswered h013 and original 12-answer accounting; reject old-stage mutations/reuse. This oracle does not execute or attest the new driver.'}
    # Every original key except the three explicit metadata/binding fields stays identical.
    protected = [k for k in old if k not in ('frozen_at_utc', 'freeze_revision', 'contract_bindings')]
    old_protected = {k: old[k] for k in protected}
    new_protected = {k: new[k] for k in protected}
    assert old_protected == new_protected
    old_hash, new_hash = sha(canonical(old_protected)), sha(canonical(new_protected))
    assert old_hash == new_hash
    dest.write_text(json.dumps(new, ensure_ascii=False, indent=2) + '\n')
    assert OLD.read_bytes() == old_bytes
    verification = {
        'schema_version': 'icfr-prospective-oracle-v2-equivalence-v1',
        'old_oracle': bind(OLD), 'new_oracle': bind(dest),
        'protected_original_keys': protected,
        'canonical_encoding': 'UTF-8 JSON ensure_ascii=False sort_keys=True separators=(comma,colon)',
        'old_protected_semantics_sha256': old_hash, 'new_protected_semantics_sha256': new_hash,
        'protected_deep_equality': True, 'original_oracle_bytes_unchanged': True,
        'per_key_canonical_sha256': {k: {'old': sha(canonical(old[k])), 'new': sha(canonical(new[k]))} for k in protected},
        'predecessor_bindings': new['predecessor_bindings'],
        'old_stage_stop_mapped_files_verified_opaque': len(mapped),
        'old_stage_stop_mapped_file_mismatches': [],
        'old_author_content_parsed': False,
        'new_stage_absent_at_freeze': True,
        'contract_bindings': new['contract_bindings'],
        'stage_spec_resources_and_native_phases_exactly_equal_archive': True,
        'stage_spec_change': 'Only new-stage isolation and predecessor preservation/prospective-freeze section.',
        'mining_spec_change': 'Executed narrative working page only: complete source-bound units, latest12/40000 UTF-8 JSON bytes, explicit omissions/charged revisit, no unit clipping, no unread data or allowance increase; existing whole-request budgets unchanged.',
        'no_new_measurement_or_research_or_admission_semantics': True,
        'caps_changed': False,
        'new_input_view_page_resource': {'max_units': 12, 'max_utf8_json_bytes': 40000, 'within_existing_request_caps': True},
        'external_api_or_network_calls': 0,
        'scope': 'Only oracle-v2 written; no stage, answer, runtime, spec or original-oracle write.'}
    (OUT / 'equivalence-evidence.json').write_text(json.dumps(verification, ensure_ascii=False, indent=2) + '\n')
    (OUT / 'stage-spec.diff').write_text(stage_diff)
    (OUT / 'mining-view-spec.diff').write_text(mining_diff)
    print(json.dumps({'new_oracle': bind(dest), 'protected_semantics_sha256': old_hash,
                      'mapped_old_files': len(mapped), 'unchanged_source_material': old['source_material'],
                      'unchanged_source_review': old['source_review']}))

if __name__ == '__main__':
    main()
