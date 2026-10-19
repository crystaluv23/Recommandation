"""Independently compare the three retained SEC source records and new view."""
import hashlib
import json
from datetime import datetime
from pathlib import Path
from stock_opportunity_agent.data.reviewed_snapshot import open_raw_info_store
from stock_opportunity_agent.data.resolution import _normalized_visible_text

ROOT = Path(__file__).resolve().parents[1]
REVIEW = Path('reports/enb-reviewed-source-inputs-20261020.json').resolve()

def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()

def instant(value):
    return datetime.fromisoformat(value.replace('Z', '+00:00'))

review = json.loads(REVIEW.read_bytes())
binding = json.loads((ROOT / 'snapshot_binding.json').read_bytes())
store = open_raw_info_store(binding['root'], reviewed_snapshot=binding)
expected_ids = {row['document_id'] for row in review['records']}
assert len(expected_ids) == 3
assert {doc.document_id for doc in store.documents} == expected_ids
rows = []
for row in review['records']:
    original = row['original_record']
    assert sha(original['path']) == original['sha256']
    raw = json.loads(Path(original['path']).read_bytes())
    body_proof, time_proof = row['proofs']
    assert sha(body_proof['artifact']['path']) == body_proof['artifact']['sha256']
    assert sha(time_proof['artifact']['path']) == time_proof['artifact']['sha256']
    cache = json.loads(Path(body_proof['artifact']['path']).read_bytes())
    submissions = json.loads(Path(time_proof['artifact']['path']).read_bytes())
    arrays = submissions['body']['filings']['recent']
    positions = [i for i, value in enumerate(arrays['accessionNumber'])
                 if value == time_proof['accession_number']]
    assert len(positions) == 1
    i = positions[0]
    assert str(submissions['body']['cik']).zfill(10) == time_proof['issuer_cik']
    assert submissions['endpoint'] == 'https://data.sec.gov/submissions/CIK0000895728.json'
    assert arrays['form'][i] == time_proof['form']
    assert arrays['primaryDocument'][i] == time_proof['primary_document']
    accepted = instant(arrays['acceptanceDateTime'][i])
    assert accepted == instant(time_proof['accepted_at']) == instant(row['reviewed_available_at'])
    assert accepted == instant(raw['available_at']) == instant(raw['published_at'])
    assert cache['endpoint'] == body_proof['endpoint']
    assert cache['body'] == raw['content']
    assert hashlib.sha256(raw['content'].encode()).hexdigest() == row['content_hash']
    loaded = store.load(row['document_id'], as_of=accepted)
    assert loaded.to_dict() == raw
    visible_chars, _ = _normalized_visible_text(raw['content'])
    visible = ''.join(visible_chars)
    if time_proof['form'] == '10-K':
        phrase = 'Liquids Pipelines consists of pipelines and terminals in Canada and the US'
        assert phrase in visible
    elif time_proof['form'] == '10-Q':
        phrase = 'Canadian dollars'
        assert phrase in visible
    else:
        phrase = '4.600%'
        assert phrase in visible
    at = visible.index(phrase)
    rows.append({'document_id': row['document_id'], 'form': time_proof['form'],
                 'accepted_at': accepted.isoformat(), 'exact_original_body': True,
                 'submissions_unique_match': True, 'literal_witness': visible[at:at+220],
                 'normalized_offset': at})
result = {'review_sha256': sha(REVIEW), 'snapshot_manifest_sha256': binding['manifest_sha256'],
          'admitted_exact_count': 3, 'records': rows, 'checks_passed': True,
          'new_network_calls': 0, 'new_model_responses': 0,
          'scope': 'Retained source identity/body/availability and exact loader only; not new model compliance or global readiness.'}
(ROOT / 'independent/root-source-checks.json').write_text(json.dumps(result, indent=2) + '\n')
print(json.dumps(result, indent=2))
