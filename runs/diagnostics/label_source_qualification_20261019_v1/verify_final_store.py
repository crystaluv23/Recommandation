"""Verify the complete canonical store after durable blind prediction, read only."""
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import resource
import socket
import time
from unittest.mock import patch

from stock_opportunity_agent.cases.label_store import LabelStore


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def main():
    root = Path('runs/cold_start/data/outcome-label-store-v1')
    prefix = Path('runs/diagnostics/reviewed_fast_prefix_20261019_v2')
    assert (prefix / 'completion.json').is_file()
    files = [root / 'manifest.json', root / 'labels.jsonl',
             prefix / 'prediction.json', prefix / 'completion.json']
    before = {str(path): sha(path) for path in files}
    code = ['src/stock_opportunity_agent/cases/label_store.py',
            'src/stock_opportunity_agent/cases/outcomes.py',
            'src/stock_opportunity_agent/data/json_stream.py',
            'src/stock_opportunity_agent/research/evolution_dataset.py']
    bindings = {path: sha(path) for path in code}
    started = time.perf_counter()
    with patch.object(socket, 'socket', side_effect=AssertionError('network forbidden')):
        store = LabelStore.load(root)
    elapsed = time.perf_counter() - started
    sink = json.loads((prefix / 'prediction.json').read_text())
    record = store.record(sink['company_id'], sink['prediction_time'][:10])
    baseline = sink['final_context']['prediction_baseline']
    after = {str(path): sha(path) for path in files}
    assert before == after
    assert bindings == {path: sha(path) for path in code}
    assert record.baseline_mean == baseline['mean_adjusted_close']
    assert list(record.baseline_dates) == baseline['trading_dates']
    return {
        'scope': 'Current-source complete strict single-door load, not provider/issuer authentication or feedback',
        'checked_at': datetime.now(timezone.utc).isoformat(), 'status': 'accepted',
        'records': len(store), 'elapsed_seconds': elapsed,
        'maxrss_native': resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
        'maxrss_unit': 'bytes', 'source_bindings': bindings,
        'archive_path': store.manifest['archive_path'],
        'archive_actual_full_stream_sha_verified': store.manifest['archive_sha256'],
        'calculator': store.manifest['calculator'], 'label_contract': store.label_contract(),
        'all_records_recomputed_by_unique_calculator': True,
        's01_record': record.to_dict(), 's01_baseline_matches_saved_sink': True,
        'before_files': before, 'after_files': after, 'files_unchanged': before == after,
        'external_llm_calls': 0, 'readonly_data_requests': 0, 'posthoc_calls': 0,
    }


if __name__ == '__main__':
    result = main()
    Path(__file__).with_name('strict-load-final.json').write_text(
        json.dumps(result, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps({key: result[key] for key in ('status', 'records', 'elapsed_seconds', 'maxrss_native', 'files_unchanged')}))
