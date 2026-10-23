"""Freeze metadata-only prospective v4; no stage, author, network or old writes."""
from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import socket
import subprocess
import sys
import tarfile
from unittest.mock import patch

sys.dont_write_bytecode = True
ROOT = Path('/Users/l/Project/Recommandation')
sys.path.insert(0, str(ROOT))
from scripts import run_icfr_native_capability_stage as stage

OUT = Path(__file__).resolve().parent
ORIGINAL = stage.BASE / 'oracle/acceptance-obligations.json'
PREVIOUS = stage.PRIOR_ORACLE
DEST = stage.ORACLE
ARCHIVE = stage.BASE / 'frozen-runtime-5fcf473b.tar.gz'
HEAD = '5fcf473b25b4c26cd2e4e0748844ac5f690b4ce2'
ORIGINAL_SEMANTICS = '4951c16c4d3cb976595e0ca12d16388fb13b85e7096fc34831e728ab55914429'


def semantic_digest(value):
    """Use exactly the compact JSON digest of the original independent freeze."""
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True,
                                    separators=(',', ':')).encode()).hexdigest()


def main():
    """Reverify immutable authority, then exclusively create code archive and oracle."""
    assert OUT == DEST.parent
    assert not DEST.exists() and not ARCHIVE.exists(), 'refusing overwrite'
    assert not stage.STAGE_ROOT.exists(), 'no stage may precede oracle freeze'
    assert subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT).decode().strip() == HEAD
    old_paths = [stage.BASE / name / 'acceptance-obligations.json'
                 for name in ('oracle', 'oracle-v2', 'oracle-v3')]
    old_bytes = {str(path): path.read_bytes() for path in old_paths}
    originals = {str(path): json.loads(old_bytes[str(path)]) for path in old_paths}
    for path in old_paths:
        assert old_bytes[str(path)] == subprocess.check_output(
            ['git', 'show', 'HEAD:' + str(path.relative_to(ROOT))], cwd=ROOT)
    original, previous = originals[str(ORIGINAL)], originals[str(PREVIOUS)]
    protected = [key for key in original if key not in
                 ('frozen_at_utc', 'freeze_revision', 'contract_bindings')]
    semantics = {key: original[key] for key in protected}
    assert semantic_digest(semantics) == ORIGINAL_SEMANTICS
    assert all(all(value[key] == original[key] for key in protected) for value in originals.values())

    code = stage._code()
    assert len(code) == 182 and len({row['path'] for row in code}) == 182
    controls, old_control_rows = stage._stopped_predecessors()
    assert len(controls) == 3 and len(old_control_rows) == 976
    assert [[row['answered_unique_requests'], row['logical_reservations']] for row in controls] == [
        [12, 2001316], [11, 1837419], [10, 2055941]]
    historical = controls[-1]['resource_prefix']
    assert list(stage._terminal_resource_prefix(historical)) == list(historical['answered_records'])
    assert historical['answered_usage'] == [10, 2055941]
    source = stage.read(stage.MATERIAL / 'material-obligations-frozen.json')
    definitions = stage.read(stage.MATERIAL / 'function-and-definition-map.json')['stable_registry18']
    factory = stage.read(stage.PARENT / 'factory-input.json')
    stage._accepted_prefix_authority(source)
    stage._check(source['source_document_bindings'] + source['definition_bindings'])
    stage._check([row['materialized_skill'] for row in definitions if row.get('materialized_skill')])
    assert len(source['source_document_bindings']) == 263 and len(definitions) == 18
    assert len(source['dev8']) == 8 and len(factory['backlog_needs']) == 265
    assert len(factory['meta_memory_disclosures']) == 6
    assert factory['label_map'] == source['authorized_original_group_map']
    assert original['fixed_denominators']['pipeline_positive_control'] == 1
    assert original['fixed_denominators']['consumer_source_controls'] == 4
    assert tuple(original['fixed_denominators']['consumer_case_refs']) == stage.CONTROLS
    assert stage.SCOPE_LIMITS == {'global': (728, 56 * stage.MIB), 'mining': (80, 12 * stage.MIB),
                                'candidate': (300, 16 * stage.MIB), 'fast': (12, 3 * stage.MIB)}
    assert stage.LIMITS == {'max_request_tokens': 262144, 'max_structured_corrections': 1,
                           'structured_reasoning_token_reserve': 0, 'max_local_role_calls': 728}
    for key in ('source_review', 'source_material'):
        assert stage.binding(previous[key]['path']) == previous[key]

    # Archive actual current files, including any already-authorized uncommitted
    # spec bytes; a git revision alone does not describe those working-tree bytes.
    stage._check(code)
    with tarfile.open(ARCHIVE, mode='x:gz') as archive:
        for row in code:
            path = Path(row['path'])
            archive.add(path, arcname=str(path.relative_to(ROOT)), recursive=False)
    with tarfile.open(ARCHIVE, mode='r:gz') as archive:
        assert len(archive.getmembers()) == 182
        for row in code:
            name = str(Path(row['path']).relative_to(ROOT))
            assert hashlib.sha256(archive.extractfile(name).read()).hexdigest() == row['sha256']
    runtime = stage.binding(ARCHIVE)
    refreshed = {row['path']: stage.binding(row['path']) for row in previous['contract_bindings']}
    refreshed.update({row['path']: row for row in code})
    contracts = [refreshed[path] for path in sorted(refreshed)]
    predecessor_bindings = [row[key] for row in controls
                            for key in ('stop_receipt', 'runtime_archive', 'pending_progress') if key in row]
    new = deepcopy(previous)
    new['frozen_at_utc'] = datetime.now(timezone.utc).isoformat()
    new['freeze_revision'] = previous['freeze_revision'] + 1
    new['contract_bindings'] = contracts
    new['predecessor_bindings'] = predecessor_bindings
    new['historical_resource_prefix'] = deepcopy(historical)
    new['runtime_archive'] = runtime
    new['prospective_revision'] = {
        'evaluation_destination': str(stage.STAGE_ROOT), 'oracle_destination': str(DEST),
        'source_oracle': stage.binding(PREVIOUS), 'original_semantic_oracle': stage.binding(ORIGINAL),
        'new_actor_stage_existed_at_freeze': False, 'new_candidate_or_consumer_outputs_read': False,
        'old_author_response_semantics_used_to_change_oracle': False,
        'source_stability_authority': 'Parent explicitly declared product source/spec stable for this freeze after independent budget/recovery counterreview.',
        'purpose': 'Actual post-repair code-version evaluation, retaining source population, measurement/admission semantics, original old failures and denominators; reference representation, query-origin navigation and historical resource preservation are the repaired code paths. No added calls or resource ceiling.',
        'old_controls': controls, 'old_denominators_not_rewritten': True,
        'new_fixed_denominators_are_independent': True,
        'driver_obligation': 'Never reenter any of the three old stages or import their answers/cache/actions. Charge the immutable v3 historical prefix once to global and Mining, preserve all original ceilings, and expose/reverify the remaining same-account resources at native request and reconstruction boundaries.',
        'immutable_historical_resource_prefix': deepcopy(historical),
        'remaining_mining': [70, 10526971], 'remaining_global': [718, 56664315],
        'runtime_revision': HEAD, 'runtime_archive': runtime, 'runtime_source_count': len(code),
        'not_claimed': ['fresh model compliance', 'candidate capability passed', 'published or reused new Signal',
                        'magnitude', 'committed business S8', 'independent benefit', 'whole MVP']}
    allowed_changed = {'frozen_at_utc', 'freeze_revision', 'contract_bindings',
                       'predecessor_bindings', 'prospective_revision'}
    changed_previous = [key for key in previous if previous[key] != new[key]]
    assert set(changed_previous) <= allowed_changed
    assert set(new) - set(previous) == {'historical_resource_prefix', 'runtime_archive'}
    assert all(new[key] == original[key] for key in protected)
    assert semantic_digest({key: new[key] for key in protected}) == ORIGINAL_SEMANTICS
    stage._check(code + contracts + predecessor_bindings + old_control_rows)
    assert stage._stopped_predecessors()[0] == controls
    assert all(path.read_bytes() == old_bytes[str(path)] for path in old_paths)
    assert not stage.STAGE_ROOT.exists()
    stage.save(DEST, new)
    evidence = {
        'schema_version': 'icfr-prospective-oracle-v4-equivalence-v1',
        'reviewer': '/root/budget_counterreview', 'runtime_revision': HEAD,
        'original_oracles': [stage.binding(path) for path in old_paths], 'new_oracle': stage.binding(DEST),
        'protected_original_keys': protected, 'deep_equal_protected_semantics': True,
        'original_protected_semantics_sha256': ORIGINAL_SEMANTICS,
        'per_protected_key_sha256': {key: {
            'original': semantic_digest(original[key]),
            'v2': semantic_digest(originals[str(old_paths[1])][key]),
            'v3': semantic_digest(previous[key]), 'v4': semantic_digest(new[key])} for key in protected},
        'changed_v3_metadata_keys': changed_previous,
        'added_v4_metadata_keys': sorted(set(new) - set(previous)),
        'all_other_v3_fields_equal': True, 'old_oracle_bytes_unchanged': True,
        'new_stage_absent_at_freeze': True, 'new_production_answers': 0,
        'source_population': {'documents': 263, 'dev_cases': 8, 'stable_versions': 18,
                              'backlog_needs': 265, 'meta_memory_disclosures': 6,
                              'fixed_candidate_denominator': 1, 'fixed_consumer_denominator': 4,
                              'consumer_case_refs': list(stage.CONTROLS)},
        'scope_limits': stage.SCOPE_LIMITS, 'transport_limits': stage.LIMITS,
        'historical_resource_prefix': historical,
        'remaining_mining': [70, 10526971], 'remaining_global': [718, 56664315],
        'runtime_archive': runtime, 'runtime_source_count': 182,
        'runtime_source_bindings': code, 'archive_members_byte_equal_sources': True,
        'contract_bindings': contracts, 'predecessor_bindings': predecessor_bindings,
        'predecessor_controls': controls,
        'actual_native_predecessor_readonly_check': {'helper': '_stopped_predecessors',
            'verified_rows': len(old_control_rows), 'bindings': old_control_rows,
            'actual_accounting': [[12, 2001316], [11, 1837419], [10, 2055941]],
            'pending_identity_answer_absence_and_status_verified': True,
            'v3_seal_and_all_file_bytes_unchanged': True},
        'external_api_network_get_new_label_calls': 0,
        'freeze_script': stage.binding(Path(__file__))}
    stage.save(OUT / 'equivalence-evidence.json', evidence)
    assert all(path.read_bytes() == old_bytes[str(path)] for path in old_paths)
    assert stage._stopped_predecessors()[0] == controls
    assert stage._code() == code and not stage.STAGE_ROOT.exists()
    print(json.dumps({'oracle': stage.binding(DEST), 'archive': runtime,
                      'protected_semantics_sha256': ORIGINAL_SEMANTICS,
                      'runtime_source_count': len(code), 'predecessor_rows': len(old_control_rows),
                      'new_stage_exists': False, 'new_production_answers': 0}))


if __name__ == '__main__':
    def forbidden(*args, **kwargs):
        raise AssertionError('freeze network tripwire')
    with patch.object(socket, 'create_connection', forbidden), patch.object(socket.socket, 'connect', forbidden):
        main()
