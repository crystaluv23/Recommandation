"""Inspect saved projections and one bound Q1 source; no Store or Signal calls."""
from pathlib import Path
import hashlib
import json
from stock_opportunity_agent.data.raw_info import RawInfoDocument
from stock_opportunity_agent.research.evolution_core import _company_facts_context
from stock_opportunity_agent.research.evolution_signal_roles import MAX_LLM_SIGNAL_CONTEXT_CHARS

OUT = Path(__file__).resolve().parent
read = lambda p: json.loads(Path(p).read_bytes())
bind = lambda p: {'path': str(Path(p).resolve()), 'sha256': hashlib.sha256(Path(p).read_bytes()).hexdigest()}
result = read(OUT/'result.json')
facts = read(OUT/'latest-facts.json')
manifest_path = Path(result['snapshot']['root'])/'reviewed_snapshot.json'
manifest = read(manifest_path)
latest_ids = {f['document_id'] for f in facts['rows']}
assert len(latest_ids) == 1
row = next(r for r in manifest['documents'] if r['document_id'] in latest_ids)
path = Path(result['snapshot']['root'])/row['path']
assert bind(path)['sha256'] == row['sha256']
document = RawInfoDocument.from_dict(read(path))
context = _company_facts_context(document, max_content_chars=MAX_LLM_SIGNAL_CONTEXT_CHARS,
                                query=result['request']['query'])
checks = {}
for name in ('native-projection.json', 'counterfactual-projection.json'):
    payload = read(OUT/name)
    rows = payload['native_projection_rows']
    checks[name] = {
        'projection_count':len(rows),
        'projection_characters':sum(len(r['exact_text']) for r in rows),
        'rows_with_fact_context':sum('fact_context' in r for r in rows),
        'latest_fact_visibility':[
            {'tag':f['tag'], 'period_end':f['end'], 'unit':f['unit'],
             'same_document_windows':[r['projection_id'] for r in rows if r['document_id']==f['document_id']],
             'whole_literal_contained_in_windows':[r['projection_id'] for r in rows
                if r['document_id']==f['document_id'] and f['exact_span'] in r['exact_text']],
             'tag_visible_in_windows':[r['projection_id'] for r in rows
                if r['document_id']==f['document_id'] and f['tag'] in r['exact_text']]}
            for f in facts['rows']],
    }
body = json.loads(document.content)
output = {
    'source':bind(path), 'schema_version':body['schema_version'], 'facts_shape':type(body['facts']).__name__,
    'native_company_facts_context_returns_none':context is None,
    'native_helper_source':bind('src/stock_opportunity_agent/research/evolution_core.py'),
    'single_projection_source':bind('src/stock_opportunity_agent/research/evolution_signal_roles.py'),
    'actual_readable_character_cap':MAX_LLM_SIGNAL_CONTEXT_CHARS,
    'projection_checks':checks,
    'measurement_not_executed':True,
    'precision_note':'Initial probe latest_exact_fact_projection_matches used chunk equality and was insufficient as a visibility test; this artifact uses complete fact literal containment within the same bound document window. Neither is a transmitted model request.',
    'scope_limit':'Generic edge correction may disclose bounded overlaps only from current selected-source lineage; it cannot retrieve an unselected document. No correction/model behavior was executed.',
}
(OUT/'readability-check.json').open('x').write(json.dumps(output,indent=2,sort_keys=True)+'\n')
print(json.dumps(output,indent=2))
