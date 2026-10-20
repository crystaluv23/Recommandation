"""Read actual saved inputs with the native fact parser; never execute a Signal."""
from datetime import datetime
import hashlib
import json
from pathlib import Path

from stock_opportunity_agent.data.raw_info import RawInfoDocument
from stock_opportunity_agent.signal_library import _sec_facts, _CASH_TAGS

ROOT = Path('/Users/l/Project/Recommandation')
STAGE = ROOT / 'runs/diagnostics/reviewed_gpre_capture_snapshot_20261021_v1/stage'
OUT = Path(__file__).resolve().parent

def read(path):
    return json.loads(Path(path).read_bytes())

def binding(path):
    path = Path(path).resolve()
    return {'path': str(path), 'sha256': hashlib.sha256(path.read_bytes()).hexdigest()}

plan = read(STAGE / 'plan.json')
review = read(STAGE / 'source-review.json')
originals = {r['document_id']: r['original_record'] for r in review['records'] if r['verdict'] == 'admitted'}
group = read(STAGE / 'latest_v12.json')
resolution = next(r['resolution'] for r in group['resolutions'] if r['signal_ref'] == 'cash_reserves:v2')
selected = tuple(RawInfoDocument.from_dict(read(originals[r['document_id']]['path'])) for r in resolution['documents'])
q1_id = 'rawcap:v1:64c9e4f193885e37ae497a75841bec6dec372f9fddf1ef7649710c28c40fc902'
q1 = RawInfoDocument.from_dict(read(originals[q1_id]['path']))
cutoff = datetime.fromisoformat(plan['case']['prediction_time'])
cash = lambda docs: tuple(f for f in _sec_facts(docs, cutoff) if f.tag in _CASH_TAGS and f.start is None)
selected_cash, q1_cash = cash(selected), cash((q1,))
latest_selected = max(selected_cash, key=lambda f: (f.end, f.filed, f.document.document_id))
latest_q1 = max(q1_cash, key=lambda f: (f.end, f.filed, f.document.document_id))
narratives = [d for d in selected if d.document_id == 'sec:cik_0001309402:000130940225000089']
assert len(narratives) == 1 and not _sec_facts(tuple(narratives), cutoff)
assert q1_id not in {d.document_id for d in selected}
assert latest_selected.end == '2023-12-31' and latest_q1.end == '2025-03-31'
result = {'scope': 'Actual saved resolution/originals and native pure parser only; no Store, resolver, Signal execution, source write, model, network or labels.',
    'signal_ref': 'cash_reserves:v2', 'selected_documents': len(selected),
    'latest_Q1_narrative_selected': True, 'narrative_native_fact_count': 0,
    'typed_Q1_not_selected_but_native_readable': True,
    'selected_latest_cash_period': latest_selected.end, 'selected_latest_cash_unit': latest_selected.unit,
    'available_typed_Q1_cash_period': latest_q1.end, 'available_typed_Q1_cash_unit': latest_q1.unit,
    'resolution_contract_satisfied': resolution['coverage']['contract_satisfied'],
    'selection_truncated': resolution['coverage']['selection_truncated'],
    'bindings': [binding(STAGE / 'plan.json'), binding(STAGE / 'latest_v12.json'),
                 *[binding(originals[d.document_id]['path']) for d in (*selected, q1)]],
    'limits': 'This proves stale selected cash inputs to the existing parser, not an executed Signal result or all seven measurements.'}
(OUT / 'root-cash-readability-result.json').write_text(json.dumps(result, indent=2) + '\n')
print(json.dumps(result, ensure_ascii=False))
