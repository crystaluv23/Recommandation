"""One authorized temporary native integration, zero answers or dispatches."""
from pathlib import Path
import json
import shutil
import tempfile
import time
import traceback
from unittest.mock import patch
from scripts import run_reviewed_slow_feedback_stage as stage
from stock_opportunity_agent.artifacts import atomic_write_json, canonical_json_hash

OUT = stage.REPO / 'runs/diagnostics/imported_slow_method_view_20261021_v1/oracle/temp-native-preflight'
if (OUT / 'result.json').exists() or (OUT / 'stage-artifacts').exists():
    raise RuntimeError('single preflight result already exists; no rerun')
formal = stage.STAGE_ROOT
sources = {stage.CASES, stage.OLD_CONTRACT, stage.SOURCE / 'completed-files.json'}
sources.update(path for root in (stage.SOURCE / 'stage', stage.REVIEWED) for path in root.rglob('*') if path.is_file())
reviewed = stage.read(stage.REVIEWED / 'reviewed_snapshot.json')
review_path = Path(reviewed['source_review']['path'])
sources.add(review_path)

def original_bindings(value):
    if isinstance(value, dict):
        if isinstance(value.get('path'), str) and isinstance(value.get('sha256'), str):
            path = Path(value['path'])
            if path.is_absolute() and path.is_file():
                if path.name in {'labels.jsonl', 'label_manifest.json'} or 'locked_test' in str(path).lower():
                    raise RuntimeError('unexpected forbidden label source binding')
                sources.add(path)
        for child in value.values():
            original_bindings(child)
    elif isinstance(value, list):
        for child in value:
            original_bindings(child)
original_bindings(stage.read(review_path))
history = stage.read(stage.SOURCE / 'stage/slow_history/manifest.json')['manifest']
source_root = Path(history['source_workspace'])
for field, prefix in [('registry_definition_files', Path('signals')), ('cycle_artifacts', Path()), ('candidate_files', Path())]:
    sources.update(source_root / prefix / row['path'] for row in history[field])
before = [stage.binding(path) for path in sorted(sources)]
atomic_write_json(OUT / 'sources-before.json', {'bindings': before, 'hash': canonical_json_hash(before)})
result = {'scope': 'single_temp_native_integration_zero_answers_not_formal_stage',
          'external_llm_api_calls': 0, 'dispatches': 0, 'submitted_answers': 0,
          'production_connections_patched': [], 'only_patch': 'STAGE_ROOT',
          'source_binding_count': len(before), 'formal_root_before_exists': formal.exists()}
started = time.monotonic()
with tempfile.TemporaryDirectory(prefix='reviewed-slow-native-preflight-') as temporary:
    root = Path(temporary) / 'stage'
    result['temporary_runtime_root'] = str(root)
    try:
        with patch.object(stage, 'STAGE_ROOT', root):
            result['prepare'] = stage.prepare(root)
            if result['prepare']['status'] == 'prepared_not_dispatched':
                result['advance'] = stage.advance(root)
    except BaseException as error:
        result['harness_error'] = {'type': type(error).__name__, 'error': str(error), 'traceback': traceback.format_exc()}
    finally:
        if root.exists():
            shutil.copytree(root, OUT / 'stage-artifacts')
        result['elapsed_seconds'] = time.monotonic() - started
        result['inbox_count'] = len(list((root / 'exchange/inbox').glob('*.json')))
        result['answer_count'] = len(list((root / 'exchange/outbox').glob('*.txt')))
        result['receipt_count'] = len(list((root / 'exchange/receipts').glob('*.json')))
after = [stage.binding(path) for path in sorted(sources)]
atomic_write_json(OUT / 'sources-after.json', {'bindings': after, 'hash': canonical_json_hash(after)})
result['sources_unchanged'] = before == after
result['formal_root_after_exists'] = formal.exists()
result['not_model_success_or_S1_S2_acceptance'] = True
atomic_write_json(OUT / 'result.json', result)
print(json.dumps(result, ensure_ascii=False, sort_keys=True, indent=2))
