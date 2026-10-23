"""Private, read-only audit of exact BURU source navigation; never dispatch a role."""
from __future__ import annotations
import datetime
import hashlib
import json
from pathlib import Path
import re
import sys
sys.dont_write_bytecode = True
ROOT = Path('/Users/l/Project/Recommandation')
sys.path.insert(0, str(ROOT))
from stock_opportunity_agent.data.raw_info import RawInfoDocument
from stock_opportunity_agent.data.disclosure import _readable_text, _filing_sections, document_card, raw_span_view
from stock_opportunity_agent.research.evolution_core import _query_relevant_excerpt, _normalized_projection_text
from stock_opportunity_agent.research.mining_agent_tools import _verbatim_window
BASE = ROOT / 'runs/diagnostics/icfr_native_capability_20261023_v1'
STAGE = BASE / 'stage-v3'
OUT = ROOT / 'runs/diagnostics/mining_catalog_working_context_20261023_v1/source-navigation-boundary'
MATERIAL = ROOT / 'runs/diagnostics/mining_capability_frontier_20261023_v1/independent/material-obligations-frozen.json'


def sha(raw):
    """Hash exact retained bytes."""
    return hashlib.sha256(raw).hexdigest()


def bind(p):
    """Bind an audit input file; this does not assert external authenticity."""
    p = Path(p)
    return {'path': str(p), 'sha256': sha(p.read_bytes())}


def load(p):
    """Read a selected local evidence JSON."""
    return json.loads(Path(p).read_text())


def main():
    """Read exact two inboxes and two filings; save audit-only source coordinates."""
    material = load(MATERIAL)
    manifest = load(STAGE / 'manifest.json')
    protected_paths = {Path(b['path']) for b in material['source_document_bindings'] + manifest['code']}
    for directory in [STAGE, BASE / 'stage', BASE / 'stage-v2', BASE / 'oracle', BASE / 'oracle-v2', BASE / 'oracle-v3']:
        protected_paths.update(p for p in directory.rglob('*') if p.is_file())
    before = [bind(p) for p in sorted(protected_paths)]
    assert all(bind(b['path']) == b for b in manifest['code'])
    baseline_path = OUT / 'protected-inputs-before.json'
    if baseline_path.exists():
        assert load(baseline_path)['files'] == before, 'Initial protected baseline drift'
    else:
        baseline_path.write_text(json.dumps({'schema_version': 'read-only-navigation-protected-inputs-v1', 'files': before, 'code_files': len(manifest['code']), 'authorized_source_documents': len(material['source_document_bindings'])}, indent=2) + '\n')
    prior = load(ROOT / 'runs/diagnostics/reviewed_gpre_capture_snapshot_20261021_v1/stage/source-review.json')
    prior_by_id = {r['document_id']: r for r in prior['records']}
    source_results = []
    for number in [1506, 1507]:
        p = ROOT / f'runs/diagnostics/reviewed_gpre_capture_snapshot_20261021_v1/stage/snapshot/documents/{number}.json'
        source = load(p)
        doc = RawInfoDocument.from_dict(source)
        readable, origins = _readable_text(doc)
        sections = _filing_sections(readable, origins)
        card = document_card(doc, include_sections=True)
        anchors = []
        for phrase in ['internal control over financial reporting was not effective', 'material weakness', 'have not been able to remediate', 'not include a report', 'December 31, 2024', 'March 31, 2025']:
            hits = list(re.finditer(re.escape(phrase), readable, re.I))
            for m in hits:
                # Preserve entire containing raw paragraph where reasonably bounded.
                at = origins[m.start()][0]
                start, end = doc.content.rfind('<p', 0, at), doc.content.find('</p>', at) + 4
                if not 0 <= start < at < end or end - start > 14000:
                    start, end = origins[max(0, m.start()-200)][0], origins[min(len(origins)-1, m.end()+500)][1]
                raw = doc.content[start:end]
                anchors.append({'matched_phrase': phrase, 'raw_start': start, 'raw_end': end, 'raw_sha256': sha(raw.encode()), 'raw_span': raw, 'rendering': ' '.join(re.sub('<[^>]+>', ' ', raw).split())})
        # Deduplicate large date-repetition excerpts; keep last 3 date-clock paragraphs only.
        anchors = [a for a in anchors if a['matched_phrase'] not in ['December 31, 2024', 'March 31, 2025']] + [a for a in anchors if a['matched_phrase'] in ['December 31, 2024', 'March 31, 2025']][-3:]
        query_rows = []
        for query in ['internal control financial reporting material weakness', 'controls procedures']:
            excerpt, clipped = _query_relevant_excerpt(doc, query=query, max_chars=600)
            raw = _verbatim_window(doc.content, excerpt)
            positions = [m.start() for m in re.finditer(re.escape(raw), doc.content)] if raw else []
            projected, runs = _normalized_projection_text(doc.content)
            exact_positions = [m.start() for m in re.finditer(re.escape(excerpt), projected)]
            exact_origins = []
            def raw_origin(index, end=False):
                run = next(r for r in runs if r[0] <= index < r[1])
                if run[1]-run[0] == run[3]-run[2]:
                    return run[2] + index-run[0] + int(end)
                return run[3] if end else run[2]
            for index in exact_positions:
                a, b = raw_origin(index), raw_origin(index+len(excerpt)-1, True)
                exact_origins.append({'projection_start': index, 'projection_end': index+len(excerpt),
                                      'raw_start': a, 'raw_end': b,
                                      'raw_span_sha256': sha(doc.content[a:b].encode()),
                                      'projected_substring_equals_selected_excerpt': projected[index:index+len(excerpt)] == excerpt})
            query_rows.append({'query': query, 'helper': '_query_relevant_excerpt(max_chars=600)', 'excerpt': excerpt, 'excerpt_sha256': sha(excerpt.encode()), 'bounded_excerpt': clipped, 'internal_verbatim_window': raw, 'internal_verbatim_window_sha256': sha(raw.encode()), 'internal_raw_positions': positions, 'true_projection_origin_bindings': exact_origins, 'verbatim_window_is_true_projection_origin': bool(exact_origins) and positions == [r['raw_start'] for r in exact_origins], 'author_visibility_limit': 'Controller fetch action returns counts/titles and catalog cardinality; neither excerpt nor exact_span/raw anchor is emitted in model_view or catalog cards. These coordinates are audit-only, not a production answer.'})
        record = prior_by_id[doc.document_id]
        proofs = []
        for proof in record['proofs']:
            artifact = load(proof['artifact']['path'])
            assert bind(proof['artifact']['path']) == proof['artifact']
            if proof['kind'] == 'sec_static_archive_body':
                assert artifact['body'] == doc.content and artifact['endpoint'] == source['metadata']['source_url']
                proofs.append({'kind': proof['kind'], 'artifact': proof['artifact'], 'endpoint': artifact['endpoint'], 'retrieved_at': artifact['retrieved_at'], 'full_body_equal': True})
            else:
                sub = artifact['body']; arrays = sub['filings']['recent']; i = arrays['accessionNumber'].index(source['metadata']['accession_number']); row = {k:v[i] for k,v in arrays.items()}
                assert str(sub['cik']).zfill(10) == source['metadata']['cik']
                assert datetime.datetime.fromisoformat(row['acceptanceDateTime'].replace('Z','+00:00')) == doc.available_at == doc.published_at
                proofs.append({'kind': proof['kind'], 'artifact': proof['artifact'], 'endpoint': artifact['endpoint'], 'retrieved_at': artifact['retrieved_at'], 'exact_submission_row': row})
        # All sections retained here solely for independent navigation audit.
        source_results.append({'source_number': number, 'source': bind(p), 'metadata': {k:v for k,v in source.items() if k!='content'}, 'raw_chars': len(doc.content), 'visible_chars': len(readable), 'all_matcher_sections': sections, 'card': card, 'raw_anchors': anchors, 'query_diagnostics': query_rows, 'provenance': proofs})
    inboxes=[]
    for name,h in [('h009','d1d559b9507c05367c0689a1059d748023d7bd542e7cfd4c684b8ab9f585b649'),('h010','6ddf18ff80a95cceb9c9d5b65e46b82fceadd76f55d05938e3006b7fa5faf597')]:
        p=STAGE/'exchange/inbox'/f'{h}.json';d=load(p);v=json.loads(d['messages'][1]['content']);annual=next(c for item in v['catalog_observations']['items'] if item['scope']=='evidence' for c in item['result']['items'] if c.get('raw_chars')==4049846)
        inboxes.append({'name':name,'inbox':bind(p),'request_hash':h,'annual_card':annual,'available_actions':v['available_actions'],'budget':v['budget'],'tool_contracts':v['tool_contracts'],'catalog_observations':[{'scope':r['scope'],'arguments':r['arguments'],'response_page':{k:z for k,z in r['result'].items() if k!='items'}} for r in v['catalog_observations']['items']], 'last_action_result':v['last_action_result'],'read_progress':v['narrative_read_progress']})
    after=[bind(p) for p in sorted(protected_paths)]
    assert before==after, 'Protected input changed during read-only diagnostic'
    result={'schema_version':'private-source-navigation-boundary-v1','privacy':'Independent audit only; no source hints, offsets or conclusions to authors/candidates.', 'exact_inboxes':inboxes,'sources':source_results,'code_bindings':[bind(ROOT/p) for p in ['src/stock_opportunity_agent/data/disclosure.py','src/stock_opportunity_agent/research/mining_agent_tools.py','src/stock_opportunity_agent/research/mining_controller.py','src/stock_opportunity_agent/research/evolution_core.py']], 'protected_inputs':{'before_file':bind(OUT/'protected-inputs-before.json'),'files':len(before),'all_bytes_unchanged':True,'code_files':len(manifest['code']),'authorized_source_documents':263},'scope':{'external_api_network_get':0,'new_model_answers':0,'stage_advance_reentry':0,'production_changes':0,'cost_recalculation':'Not performed; separate reviewer owns exact cost.'}}
    (OUT/'bindings-evidence.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
    for r in source_results:
        print('SOURCE',r['source_number'],'SECTIONS',len(r['all_matcher_sections']))
        for section in r['all_matcher_sections']:
            print(section['section_id'],section['raw_start'],section['heading'])
        for a in r['raw_anchors']:
            if a['matched_phrase'] not in ['December 31, 2024','March 31, 2025']:
                print('ANCHOR',a['matched_phrase'],a['raw_start'],a['raw_end'],a['rendering'][:1200])
        print('QUERY',[(q['query'],q['excerpt'][:250],q['internal_raw_positions']) for q in r['query_diagnostics']])
    print('PROTECTED',len(before),'UNCHANGED',before==after)

if __name__=='__main__':main()
