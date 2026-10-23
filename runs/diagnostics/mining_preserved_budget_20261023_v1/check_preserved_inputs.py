"""Audit original controls/source hashes without entering any frozen executor."""
import hashlib
import json
from pathlib import Path
import subprocess

from scripts import run_icfr_native_capability_stage as stage

BASE = Path(__file__).resolve().parent
controls, _ = stage._stopped_predecessors()
obligations = stage.read(stage.MATERIAL / 'material-obligations-frozen.json')
stage._check(obligations['source_document_bindings'] + obligations['definition_bindings'])
oracles = []
for version in ('oracle', 'oracle-v2', 'oracle-v3'):
    path = stage.BASE / version / 'acceptance-obligations.json'
    relative = str(path.relative_to(stage.REPO))
    committed = subprocess.check_output(['git', 'show', 'HEAD:' + relative], cwd=stage.REPO)
    assert committed == path.read_bytes(), relative
    oracles.append(stage.binding(path))
result = {
    'review_kind': 'parent_deterministic_audit_not_independent_model_review',
    'controls': [{key: value for key, value in row.items() if key != 'resource_prefix'} for row in controls],
    'v3_completion_file_count': len(stage.read(stage.SEALED_STAGE_V3_ROOT / 'completion.json')['files']),
    'v3_full_file_count': sum(p.is_file() for p in stage.SEALED_STAGE_V3_ROOT.rglob('*')),
    'all_historical_answered_calls': sum(row['answered_unique_requests'] for row in controls),
    'all_historical_logical_reservations': sum(row['logical_reservations'] for row in controls),
    'inherited_branch_usage': controls[-1]['resource_prefix']['answered_usage'],
    'remaining_mining': [70, 10526971], 'remaining_global': [718, 56664315],
    'source_document_count': len(obligations['source_document_bindings']),
    'definition_bindings_count': len(obligations['definition_bindings']),
    'original_oracles_equal_committed_bytes': oracles,
    'new_oracle_exists': stage.ORACLE.exists(), 'new_stage_exists': stage.STAGE_ROOT.exists(),
    'external_api_calls': 0, 'new_production_actors': 0,
    'code': stage._code(),
    'script_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
}
assert result['source_document_count'] == 263
assert result['v3_completion_file_count'] == 312 and result['v3_full_file_count'] == 316
assert not result['new_oracle_exists'] and not result['new_stage_exists']
(BASE / 'preserved-inputs.json').write_text(json.dumps(result, indent=2) + '\n')
print(json.dumps({key: value for key, value in result.items() if key not in ('code', 'controls', 'original_oracles_equal_committed_bytes')}))
