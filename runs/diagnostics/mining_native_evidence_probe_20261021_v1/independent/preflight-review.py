"""Source/contract-only review; no product imports or native helper execution."""
from pathlib import Path
import ast
import hashlib
import json

ROOT = Path('/Users/l/Project/Recommandation/runs/diagnostics/mining_native_evidence_probe_20261021_v1')
REPO = ROOT.parents[2]
OWN = Path(__file__).resolve().parent
bindings = {}


def sha(path):
    path = Path(path)
    value = hashlib.sha256(path.read_bytes()).hexdigest()
    bindings[str(path)] = value
    return value


def read(path):
    path = Path(path)
    assert path.name not in {'approved_cases.json', 'input_manifest.json', 'labels.jsonl'}
    sha(path)
    return json.loads(path.read_text())


if __name__ == '__main__':
    assert sha(ROOT / 'probe.py') == '00c34ffab06a28c0f6dafa7e3d4e8367b6e06eae939d24cd001676a12a7614a3'
    assert sha(ROOT / 'plan.json') == '3e3416fd3f1fe830d1ece62ba9769e508c166f605ee4226c4a91e6d8c20f006e'
    assert sha(ROOT / 'spec.md') == '87ad38320f69fee93c178e49c5cbc0d17c9f50011b43a80ce0748d33a4d9d344'
    plan = read(ROOT / 'plan.json')
    assert len(plan['bindings']) == 4135
    assert plan['controls'] == ['O1-original-selection', 'O2-original-context-and-projection', 'L1-legacy-val-positive',
        'T1-small-typed-value', 'R1-role-unit-conflict', 'P1-document-selection-and-PIT', 'P2-row-PIT']
    assert plan['output_root'] == str(ROOT) and plan['execution_root'] == str(ROOT / 'execution')
    assert sha(plan['exact_inputs']['path']) == plan['exact_inputs']['sha256'] == '9e7b5674c344dd26043d1978a0b62b56d6badb1bb878427720434dd2d9f77e63'
    assert sha(plan['expectations']['path']) == plan['expectations']['sha256'] == '27e5b72f16f710d9d04dfb242d4a281e4ca3c939b6a521e059c7511b0e1f3355'
    inputs = read(plan['exact_inputs']['path']); expected = read(plan['expectations']['path'])
    assert [c['id'] for c in expected['controls']] == plan['controls']
    original = inputs['original']
    assert sha(REPO / original['path']) == original['file_sha256']
    raw = read(REPO / original['path']); body = json.loads(raw['content'])
    assert raw['document_id'] == original['document_id'] and raw['content_hash'] == original['content_hash']
    assert hashlib.sha256(raw['content'].encode()).hexdigest() == original['content_hash']
    assert raw['company_id'] == inputs['case_original']['company_id']
    assert len(original['rows']) == 4
    for witness in original['rows']:
        row = body['facts'][int(witness['locator'].split('/')[-1])]
        span = raw['content'][witness['offset_start']:witness['offset_end']]
        assert row == witness['whole_row'] and span == witness['exact_span']
        assert json.loads(span) == row and hashlib.sha256(span.encode()).hexdigest() == witness['span_sha256']
        assert 'value' in row and 'val' not in row
    assert len(inputs['synthetic_controls']) == 6
    for synthetic in inputs['synthetic_controls']:
        document = synthetic['document']
        assert synthetic['synthetic_only'] is True and document['metadata']['diagnostic_synthetic'] is True
        assert json.loads(document['content']) == synthetic['payload']
        assert hashlib.sha256(document['content'].encode()).hexdigest() == document['content_hash']
    code = (ROOT / 'probe.py').read_text(); ast.parse(code)
    assert code.index('sys.dont_write_bytecode = True') < code.index('from stock_opportunity_agent')
    assert not (ROOT / 'execution').exists()
    bound = {r['path']: r['sha256'] for r in plan['bindings']}
    for relative in ('src/stock_opportunity_agent/research/mining_agent_tools.py',
                     'src/stock_opportunity_agent/research/evolution_core.py',
                     'src/stock_opportunity_agent/data/raw_info.py',
                     'src/stock_opportunity_agent/data/reviewed_snapshot.py'):
        path = REPO / relative
        assert sha(path) == bound[str(path)]
    assert not any(Path(p).name in {'approved_cases.json', 'input_manifest.json', 'labels.jsonl', 'label_manifest.json'}
                   and '/src/' not in p for p in bound)
    report = {'status': 'PASS_bounded_static_preexecution_review; NO_NATIVE_HELPER_EXECUTED',
        'source_proof': {'original_file_body_identity_exact': True, 'four_whole_row_literals_and_character_offsets_exact': True,
            'value_only_real_rows_unchanged': True, 'six_synthetic_documents_body_hash_exact_and_explicitly_separate': True},
        'contract_alignment': {'exact_seven_controls_script_spec_v2': True,
            'real_fetch_scope': 'case008/sec_company_facts/no-query/cap1 only; O2 independently binds direct0671 and reports whether selected.',
            'projection_frontier': 'Record native context before EvidenceFacts. Only nonempty value-only context plus zero facts supports the val-only adaptation explanation; empty context remains an earlier unknown gate.',
            'period_frontier': 'R1 dual-key is an explicit synthetic bypass for index-based prior-role behavior. It cannot establish an actual typed source already produced an invalid relation.',
            'arithmetic': 'L1/R1 ratio and difference use only actual builder-produced refs. Finite output does not establish period/currency comparability, and cross-unit arithmetic is not automatically a policy violation.',
            'cross_document_boundary': 'No cross-document order reversal is executed in the fixed seven controls. The static last-write concern remains unexercised; do not claim this probe measured or repaired it.'},
        'safety_static_review': {'fixed_source_code_plan_script_checks_before_exclusive_marker': True,
            'source_only_three_attribute_case_carrier': True, 'real_1780_reviewed_store_for_original_fetch': True,
            'synthetic_documents_only_collection_no_append': True,
            'persistent_store_labels_network_model_Signal_fullprepare_forbidden': True,
            'only_empty_memory_parent_init_allowed_for_reviewed_subclass': True,
            'first_failure_and_source_drift_saved_no_retry': True, 'bytecode_disabled_before_product_imports': True,
            'execution_directory_absent_at_review': True},
        'limits': ['Only stdlib parsing, hashing and AST syntax validation ran. No product import, native helper, probe execution, Store, Signal, model/API/GET, label or approved mixed case envelope accessed by this reviewer.',
            'Four source-code bindings and directly named original/oracle/spec/plan were independently hashed. All4135 transitive bindings were not redundantly rehashed here; the runner must check all before its marker and preserve before/after.',
            'Source row literals and manifest qualification do not prove native context inclusion or source0671 measurement success; those remain actual diagnostic observations.',
            'Expected mismatches are findings, not an all-green capability criterion. Do not modify source/oracle or rerun a completed/failed execution to obtain passage.',
            'No complete EvolutionCase/Engine, full Mining, fresh model behavior, prior comparison-policy change, new Signal or research benefit is established.'],
        'bindings': bindings}
    sha(Path(__file__))
    output = OWN / 'preflight-review.json'
    output.write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps({'status': report['status'], 'sha256': sha(output)}))
