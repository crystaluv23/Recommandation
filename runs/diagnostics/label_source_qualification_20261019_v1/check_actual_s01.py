"""Post-sink read-only single-key label qualification, never a blind input."""
from datetime import date,datetime,timezone
import hashlib,json
from pathlib import Path
from stock_opportunity_agent.cases.label_store import LabelStore
from stock_opportunity_agent.cases.outcomes import SURGE_LABEL_CONTRACT,six_month_smoothed_multiple
from stock_opportunity_agent.artifacts import canonical_json_hash


def binding(path):
    path=Path(path)
    with path.open('rb') as handle: digest=hashlib.file_digest(handle,'sha256').hexdigest()
    return {'path':str(path.resolve()),'sha256':digest}


def single_symbol_from_pretty_archive(path,symbol):
    """Read one known canonical archive array with bounded memory, not a new loader."""
    prefix='    '+json.dumps(symbol)+': '
    with path.open() as handle:
        for line in handle:
            if line.startswith(prefix):
                parts=[]; depth=0; quoted=False; escaped=False; started=False
                for text in (line[len(prefix):],*()):
                    pass
                text=line[len(prefix):]
                while True:
                    for index,char in enumerate(text):
                        if quoted:
                            if escaped: escaped=False
                            elif char=='\\': escaped=True
                            elif char=='"': quoted=False
                        elif char=='"': quoted=True
                        elif char=='[': depth+=1; started=True
                        elif char==']':
                            depth-=1
                            if started and depth==0:
                                parts.append(text[:index+1]);return json.loads(''.join(parts))
                    parts.append(text);text=next(handle)
    raise ValueError('target symbol array missing')


def main():
    prefix=Path('runs/diagnostics/reviewed_fast_prefix_20261019_v2')
    sink=json.loads((prefix/'prediction.json').read_text())
    assert (prefix/'completion.json').is_file(),'label qualification requires actual durable prediction boundary'
    root=Path('runs/cold_start/data/outcome-label-store-v1')
    store=LabelStore.load(root); manifest=store.manifest
    record=store.record(sink['company_id'],sink['prediction_time'][:10])
    archive=Path(manifest['archive_path']); ab=binding(archive)
    assert ab['sha256']==manifest['archive_sha256'],'archive SHA mismatch'
    bars=single_symbol_from_pretty_archive(archive,record.symbol)
    derived=six_month_smoothed_multiple(bars,date.fromisoformat(record.as_of_date))
    current=record.to_dict(); comparable={key:current[key] for key in derived}
    anchor=sink['final_context']['prediction_baseline']
    return {'scope':'Actual s01 post-durable-sink canonical source qualification only; no Posthoc dispatch or feedback',
        'checked_at':datetime.now(timezone.utc).isoformat(),'manifest':manifest,
        'files':[binding(root/'manifest.json'),binding(root/'labels.jsonl'),ab,
                 binding('src/stock_opportunity_agent/cases/label_store.py'),binding('src/stock_opportunity_agent/cases/outcomes.py')],
        'loaded_records':len(store),'calculator_identity_matches':manifest['calculator']=='stock_opportunity_agent.cases.outcomes.six_month_smoothed_multiple',
        'label_contract_matches':manifest['label_contract']==SURGE_LABEL_CONTRACT,'archive_sha_matches':True,
        'target_record':current,'unique_calculator_recomputed':derived,'record_exactly_matches_recomputation':comparable==derived,
        'baseline_matches_saved_sink':record.baseline_mean==anchor['mean_adjusted_close'] and list(record.baseline_dates)==anchor['trading_dates'],
        'horizon_matches_saved_six_calendar_month_definition':record.horizon_end=='2026-03-30',
        'target_archive_bars':len(bars),'archive_first_date':bars[0]['as_of_date'],'archive_last_date':bars[-1]['as_of_date'],
        'provider_price_truth_authenticated_by_this_check':False,
        'loader_general_contract_gap':'load presently does not itself verify archive hash/calculator/contract/recompute; independently checked only this real key here',
        'blind_prefix_modified':False,'posthoc_calls':0,'external_llm_calls':0,'readonly_data_requests':0}
if __name__=='__main__': print(json.dumps(main(),ensure_ascii=False,indent=2))
