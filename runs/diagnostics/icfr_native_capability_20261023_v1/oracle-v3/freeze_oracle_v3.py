"""Freeze metadata-only ICFR oracle-v3 after source stability; never create a stage."""
from __future__ import annotations
import copy
import datetime
import difflib
import hashlib
import importlib.util
import json
from pathlib import Path
import sys
import tarfile
sys.dont_write_bytecode = True
ROOT = Path('/Users/l/Project/Recommandation')
sys.path.insert(0, str(ROOT))
BASE = ROOT / 'runs/diagnostics/icfr_native_capability_20261023_v1'
OUT = BASE / 'oracle-v3'
ORIGINAL = BASE / 'oracle/acceptance-obligations.json'
PREVIOUS = BASE / 'oracle-v2/acceptance-obligations.json'
DRIVER = ROOT / 'scripts/run_icfr_native_capability_stage.py'
STAGE_SPEC = ROOT / 'spec/scripts/run_icfr_native_capability_stage.md'
MINING_SPEC = ROOT / 'spec/src/stock_opportunity_agent/research/signal_mining_agent.md'
EXPECTED = {
    'spec/src/stock_opportunity_agent/research/signal_mining_agent.md': '2f62346dec4bc595a93bd8a20daf2e9541ec3a6a40e1a3653dd8c66247c1949b',
    'src/stock_opportunity_agent/research/mining_controller.py': '1f5dfc82eb2e4ec2480c4dcad1e7d030a2ac9330420964c2e75825eefa0d5dd8',
    'src/stock_opportunity_agent/research/mining_role_model.py': '105325b137c8751b11c5478b66d1fb392ab50fc8a0caff4a1f3a8d9f8ff10f70',
    'tests/test_mining_catalog_working_context.py': 'a8f00a6096546562f23e09e720642b811f915053dd276f8cf382336b4cd5c485'}


def digest(value):
    """Hash deterministic JSON to compare immutable semantic content."""
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':')).encode()).hexdigest()


def binding(path):
    """Bind exact file bytes; hashes alone are not semantic/source proof."""
    p = Path(path)
    return {'path': str(p), 'sha256': hashlib.sha256(p.read_bytes()).hexdigest()}


def main():
    """Freeze only allowed metadata changes after real read-only prerequisite checks."""
    dest = OUT / 'acceptance-obligations.json'
    if dest.exists():
        raise RuntimeError('Oracle already frozen; refusing overwrite')
    assert not (BASE / 'stage-v3').exists(), 'v3 stage already exists'
    old_bytes, previous_bytes = ORIGINAL.read_bytes(), PREVIOUS.read_bytes()
    original, previous = json.loads(old_bytes), json.loads(previous_bytes)
    protected = [k for k in original if k not in ('frozen_at_utc', 'freeze_revision', 'contract_bindings')]
    protected_original = {k: original[k] for k in protected}
    assert all(previous[k] == original[k] for k in protected)
    assert digest(protected_original) == '4951c16c4d3cb976595e0ca12d16388fb13b85e7096fc34831e728ab55914429'
    for rel, expected in EXPECTED.items():
        assert binding(ROOT / rel)['sha256'] == expected, rel
    spec = importlib.util.spec_from_file_location('icfr_v3_frozen_readonly_driver', DRIVER)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    proofs, rows = module._stopped_predecessors()
    assert len(proofs) == 2 and len(rows) == 660
    assert [(p['answered_unique_requests'], p['logical_reservations']) for p in proofs] == [(12, 2001316), (11, 1837419)]
    assert [p['pending_progress']['sha256'] for p in proofs] == [
        'c2fd2104438f94ef44402ec83f42fe4070801edd03b81fb825893006cc1f6081',
        '0fd2ba50edbab78744c09deec96a19a44ecf1f22f82e3c773fa1c21f89e1cd80']
    contracts = [binding(b['path']) for b in previous['contract_bindings']]
    for rel in EXPECTED:
        if str(ROOT / rel) not in {b['path'] for b in contracts}:
            contracts.append(binding(ROOT / rel))
    for p in [DRIVER, ROOT / 'tests/test_icfr_native_capability_stage.py']:
        if str(p) not in {b['path'] for b in contracts}:
            contracts.append(binding(p))
    for k in ('source_review', 'source_material'):
        assert binding(previous[k]['path']) == previous[k]
    new = copy.deepcopy(previous)
    new['frozen_at_utc'] = datetime.datetime.now(datetime.timezone.utc).isoformat()
    new['freeze_revision'] = previous['freeze_revision'] + 1
    new['contract_bindings'] = contracts
    new['predecessor_bindings'] = [p[k] for p in proofs for k in ('stop_receipt', 'runtime_archive', 'pending_progress')]
    new['prospective_revision'] = {
        'evaluation_destination': str(BASE / 'stage-v3'), 'oracle_destination': str(dest),
        'source_oracle': binding(PREVIOUS), 'original_semantic_oracle': binding(ORIGINAL),
        'new_actor_stage_existed_at_freeze': False,
        'new_candidate_or_consumer_outputs_read': False,
        'old_author_response_semantics_used_to_change_oracle': False,
        'source_stability_authority': 'Parent explicitly stated source stable to freeze after final driver pending-progress binding update.',
        'purpose': 'New code-version evaluation retaining issued catalog/navigation and computed working observations; no change to source population, measurement, admission semantics or resource ceilings.',
        'old_controls': proofs, 'old_denominators_not_rewritten': True,
        'new_fixed_denominators_are_independent': True,
        'driver_obligation': 'Preserve both old stages, stop receipts, exact file maps, archives, pending-progress bytes and unanswered identities. Verify actual original wire/receipt accounting; never import old answers/caches or reenter stopped roots.'}
    assert all(new[k] == original[k] for k in protected)
    # v2 additions also remain immutable except the two expressly authorized metadata records.
    changed_previous_keys = [k for k in previous if previous[k] != new[k]]
    allowed = {'frozen_at_utc', 'freeze_revision', 'contract_bindings', 'predecessor_bindings', 'prospective_revision'}
    assert set(changed_previous_keys) <= allowed
    assert digest({k: new[k] for k in protected}) == digest(protected_original)
    # Verify old source/contract/receipt bindings again immediately before the write.
    for b in contracts + new['predecessor_bindings']:
        assert binding(b['path']) == b
    assert ORIGINAL.read_bytes() == old_bytes and PREVIOUS.read_bytes() == previous_bytes
    archive = Path(proofs[1]['runtime_archive']['path'])
    with tarfile.open(archive) as retained:
        old_stage = retained.extractfile(str(STAGE_SPEC.relative_to(ROOT))).read().decode()
        old_mining = retained.extractfile(str(MINING_SPEC.relative_to(ROOT))).read().decode()
    new_stage, new_mining = STAGE_SPEC.read_text(), MINING_SPEC.read_text()
    assert old_stage.split('## Resources and real roles', 1)[1] == new_stage.split('## Resources and real roles', 1)[1]
    dest.write_text(json.dumps(new, ensure_ascii=False, indent=2) + '\n')
    evidence = {
        'schema_version': 'icfr-prospective-oracle-v3-equivalence-v1',
        'original_oracle': binding(ORIGINAL), 'previous_oracle': binding(PREVIOUS), 'new_oracle': binding(dest),
        'protected_original_keys': protected, 'original_protected_semantics_sha256': digest(protected_original),
        'v2_protected_semantics_sha256': digest({k: previous[k] for k in protected}),
        'v3_protected_semantics_sha256': digest({k: new[k] for k in protected}),
        'per_protected_key_sha256': {k: {'original': digest(original[k]), 'v2': digest(previous[k]), 'v3': digest(new[k])} for k in protected},
        'deep_equal_protected_semantics': True, 'changed_v2_keys': changed_previous_keys,
        'old_oracle_bytes_unchanged': True, 'new_stage_absent_at_freeze': True,
        'no_new_actor_answers_read': True, 'contract_bindings': contracts,
        'predecessor_bindings': new['predecessor_bindings'], 'predecessor_controls': proofs,
        'actual_native_predecessor_readonly_check': {'helper': '_stopped_predecessors', 'verified_rows': len(rows),
            'includes_original_filemaps': [336, 323], 'plus_new_v2_pending_progress_binding': 1,
            'actual_accounting': [[12, 2001316], [11, 1837419]],
            'pending_identity_answer_absence_and_status_verified': True,
            'transient_file_policy': 'Existing _files excludes progress/locks/completion; v1 stop explicitly bound progress, v2 progress now bound separately. No old map rewritten.'},
        'four_product_hashes_match_parent_final': EXPECTED,
        'resources_and_native_phases_exactly_equal_v2_archive': True,
        'source_material_binding_actual_matches': True, 'source_review_binding_actual_matches': True,
        'view_change_limits': {'catalog_observations': 'at most8 complete responses /32000 UTF-8 JSON bytes',
            'computed_statistics': 'at most12 complete ledger-derived entries /8000 UTF-8 JSON bytes',
            'no_allowance_or_semantic_increase': True,
            'computed_stale_operand_semantics': 'Later fetch/missing/mismatched operand invalidates current evidence and candidate citation; ordinary charged recomputation can restore it. No automatic recompute or new value.'},
        'not_claimed': ['new model compliance', 'new capability control passed', 'effect or magnitude', 'whole MVP'],
        'external_api_network_get_new_label_calls': 0}
    (OUT / 'equivalence-evidence.json').write_text(json.dumps(evidence, ensure_ascii=False, indent=2) + '\n')
    (OUT / 'stage-spec.diff').write_text(''.join(difflib.unified_diff(old_stage.splitlines(True), new_stage.splitlines(True), fromfile='v2-runtime/stage-spec', tofile='current/stage-spec')))
    (OUT / 'mining-view-spec.diff').write_text(''.join(difflib.unified_diff(old_mining.splitlines(True), new_mining.splitlines(True), fromfile='v2-runtime/mining-spec', tofile='current/mining-spec')))
    print(json.dumps({'new_oracle': binding(dest), 'protected_semantics_sha256': digest(protected_original), 'verified_predecessor_rows': len(rows)}))

if __name__ == '__main__':
    main()
