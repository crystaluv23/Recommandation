"""Reproduce bounded, label-free checks over four exact local SEC source chains."""
from __future__ import annotations
import datetime
import gzip
import hashlib
import html
import json
from pathlib import Path
import re

ROOT = Path('/Users/l/Project/Recommandation')
OUT = ROOT / 'runs/diagnostics/icfr_native_capability_20261023_v1/source-review'
MATERIAL = ROOT / 'runs/diagnostics/mining_capability_frontier_20261023_v1/independent/narrative-material-bindings.json'
PRIOR = ROOT / 'runs/diagnostics/reviewed_gpre_capture_snapshot_20261021_v1/stage/source-review.json'
NUMBERS = {'case-005': 1507, 'case-006': 1500, 'case-003': 1501, 'case-001': 1768}


def binding(path: str | Path) -> dict:
    """Bind a local evidence file without treating its hash as source authenticity."""
    p = Path(path)
    return {'path': str(p), 'sha256': hashlib.sha256(p.read_bytes()).hexdigest()}


def read(path: str | Path):
    """Read a local JSON evidence file."""
    return json.loads(Path(path).read_text())


def readable(raw: str) -> str:
    """Render a short raw anchor for review, retaining raw offsets separately."""
    return ' '.join(re.sub(r'<[^>]+>', ' ', html.unescape(raw)).split())


def span(content: str, start: int, end: int, kind: str) -> dict:
    """Preserve an exact source anchor and its review-only rendering."""
    raw = content[start:end]
    return {'kind': kind, 'raw_start': start, 'raw_end': end,
            'raw_span': raw, 'readable_rendering': readable(raw),
            'raw_span_sha256': hashlib.sha256(raw.encode()).hexdigest()}


def main() -> None:
    """Check only approved exact sources and write bounded provenance evidence."""
    obligations = binding(OUT / 'obligations.json')
    material = read(MATERIAL)
    prior = {r['document_id']: r for r in read(PRIOR)['records']}
    results = []
    for case_ref, number in NUMBERS.items():
        citations = [c for c in material['citations'] if c['case_ref'] == case_ref]
        src_path = Path(citations[0]['source']['path'])
        source = read(src_path)
        record = prior[source['document_id']]
        original = read(record['original_record']['path'])
        assert original == source
        body = source['content']
        assert hashlib.sha256(body.encode()).hexdigest() == source['content_hash']
        subproof = next(p for p in record['proofs'] if p['kind'] in ('sec_submissions_root', 'sec_submissions_acceptance'))
        subpath = subproof['artifact']['path']
        subcache = read(subpath)
        sub = subcache['body']
        recent = sub['filings']['recent']
        indices = [i for i, a in enumerate(recent['accessionNumber']) if a == subproof['accession_number']]
        assert len(indices) == 1
        row = {k: v[indices[0]] for k, v in recent.items()}
        issuer = str(sub['cik']).zfill(10)
        url = f"https://www.sec.gov/Archives/edgar/data/{int(issuer)}/{row['accessionNumber'].replace('-', '')}/{row['primaryDocument']}"
        assert issuer == source['metadata']['cik']
        assert row['accessionNumber'] == source['metadata']['accession_number']
        assert row['form'] == source['metadata']['form']
        assert url == source['metadata']['source_url']
        assert subcache['endpoint'] == f'https://data.sec.gov/submissions/CIK{issuer}.json'
        accepted = datetime.datetime.fromisoformat(row['acceptanceDateTime'].replace('Z', '+00:00'))
        assert accepted == datetime.datetime.fromisoformat(source['available_at'])
        assert accepted == datetime.datetime.fromisoformat(source['published_at'])
        cutoff = datetime.datetime.fromisoformat(citations[0]['source']['cutoff'])
        assert accepted < cutoff
        bodyproof = next(p for p in record['proofs'] if p['kind'].startswith('sec_static_archive_body'))
        bodypath = bodyproof['artifact']['path']
        bodyartifact = read(bodypath)
        receipt_evidence = None
        if bodyproof['kind'] == 'sec_static_archive_body':
            retained_body = bodyartifact['body']
            assert bodyartifact['endpoint'] == url
            body_retrieved = bodyartifact['retrieved_at']
            body_role = 'original_native_text_cache'
        else:
            receipt = bodyartifact['requests'][0]
            assert receipt['url'] == url == receipt['response_url']
            assert receipt['http_status'] == 200
            rawpath = Path(receipt['raw_response'])
            compressed = rawpath.read_bytes()
            assert hashlib.sha256(compressed).hexdigest() == receipt['raw_sha256']
            retained_body = gzip.decompress(compressed).decode('utf-8')
            body_retrieved = receipt['retrieved_at_utc']
            body_role = 'original_http_response_gzip_decoded'
            receipt_evidence = {'receipt': binding(bodypath), 'raw_response': binding(rawpath),
                                'http_status': receipt['http_status'], 'url': receipt['url'],
                                'response_url': receipt['response_url'],
                                'headers': {k: receipt['response_headers'][k] for k in
                                            ('Content-Encoding', 'Date', 'Last-Modified', 'x-amz-version-id')},
                                'last_modified_limit': 'Same-filing-day Last-Modified corroborates an old object; it is not proof of original acceptance-time bytes or independently verified S3 version history.'}
        assert retained_body == body
        anchors = []
        for name in ('EntityCentralIndexKey', 'EntityRegistrantName', 'DocumentType',
                     'DocumentPeriodEndDate', 'DocumentFiscalYearFocus', 'AmendmentFlag'):
            pat = r'<ix:nonNumeric\b[^>]*name=[\"\']dei:' + name + r'[\"\'][^>]*>.*?</ix:nonNumeric>'
            matches = list(re.finditer(pat, body, re.I | re.S))
            assert matches
            anchors.extend(span(body, m.start(), m.end(), 'inline_dei_' + name) for m in matches)
        comments = [span(body, m.start(), m.end(), 'document_generator_comment')
                    for m in re.finditer(r'<!--.*?-->', body[:5000], re.S)
                    if any(s in m.group() for s in ('Created:', 'Creation Date', 'AmendmentFlag_false', 'EntityCentralIndexKey'))]
        anchors.extend(comments)
        for citation in citations:
            for cited in citation['exact_raw_citations']:
                assert body[cited['raw_start']:cited['raw_end']] == cited['raw_span']
                anchors.append(span(body, cited['raw_start'], cited['raw_end'], citation['kind']))
        # Additional exact raw paragraphs, independently of the prior citation list.
        needles = (['This Annual Report does not include', 'up through March 28, 2025']
                   if number == 1501 else [])
        for needle in needles:
            at = body.find(needle)
            if at < 0:
                # HTML line breaks may separate words.
                match = re.search(r'\s+'.join(map(re.escape, needle.split())), body)
                at = match.start() if match else -1
            assert at >= 0, needle
            start = body.rfind('<p', 0, at)
            end = body.find('</p>', at) + 4
            assert 0 <= start < at < end and end - start < 12000
            anchors.append(span(body, start, end, 'additional_management_or_clock_countercheck'))
        results.append({'case_ref': case_ref, 'source_number': number,
                        'case_id': citations[0]['source']['case_id'], 'cutoff': cutoff.isoformat(),
                        'source': binding(src_path), 'original': binding(record['original_record']['path']),
                        'source_metadata': {k: v for k, v in source.items() if k != 'content'},
                        'submissions_cache': binding(subpath),
                        'submissions_request': {k: subcache[k] for k in ('endpoint', 'source_key', 'capability', 'payload_kind', 'params', 'retrieved_at')},
                        'submissions_issuer': {'cik': issuer, 'name': sub['name']},
                        'exact_submission_row': row,
                        'body_artifact': binding(bodypath), 'body_capture_role': body_role,
                        'body_retrieved_at': body_retrieved, 'receipt_evidence': receipt_evidence,
                        'body_length_characters': len(body), 'source_url': url,
                        'checks': {'snapshot_equals_original': True, 'retained_full_body_equals_source': True,
                                   'original_cache_request_matches_exact_primary_url': True,
                                   'root_cik_equals_source_and_url_issuer': True,
                                   'single_exact_accession_row': True,
                                   'row_form_and_primary_document_match': True,
                                   'acceptance_equals_available_and_published': True,
                                   'acceptance_precedes_case_cutoff': True,
                                   'input_citation_offsets_match_full_original': True},
                        'anchors': anchors,
                        'verdicts': {'exact_local_historical_source_binding': 'pass_local_binding',
                                     'affirmative_post_update_contamination': 'not_observed_in_reviewed_object_period_generator_and_anchor_checks',
                                     'historical_original_bytes_independent_remote_attestation': 'unknown',
                                     'latest_present_icfr_truth': 'not_claimed'}})
    out = {'schema_version': 'icfr-local-source-review-evidence-v1',
           'frozen_obligations': obligations, 'material_bindings': binding(MATERIAL),
           'prior_source_review_locator': binding(PRIOR), 'review_script': binding(__file__),
           'source_results': results,
           'scope': {'external_calls': 0, 'new_model_authors': 0, 'new_candidates': 0,
                     'new_business_labels_or_check_or_lockedtest_reads': 0,
                     'business_stage_mutations': 0, 'reviewed_exact_sources': 4},
           'limits': ['Local cache is retained source evidence, not signed SEC attestation.',
                      'No 2024/2025 contemporaneous capture or independent version history is established.',
                      'No source was rejected merely for 2026 retrieval.',
                      'No full-body line-by-line contamination proof or latest-as-of-filing selection claim.',
                      'No candidate schema, research direction/magnitude, admission or production result.']}
    (OUT / 'bindings-evidence.json').write_text(json.dumps(out, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps({'sources': len(results), 'checks_per_source': [sum(r['checks'].values()) for r in results],
                      'external_calls': 0, 'output': str(OUT / 'bindings-evidence.json')}))

if __name__ == '__main__':
    main()
