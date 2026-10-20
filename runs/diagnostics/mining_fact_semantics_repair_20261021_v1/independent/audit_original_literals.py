"""Audit all current native original0671 facts, without labels or stage entry."""
import dataclasses
import hashlib
import json
from pathlib import Path
import socket
import sys

def forbidden(*args,**kwargs):
    raise AssertionError('network forbidden')
socket.create_connection=forbidden
socket.socket.connect=forbidden
ROOT=Path(__file__).resolve().parents[4]
sys.path.insert(0,str(ROOT/'src'))
from stock_opportunity_agent.data.raw_info import RawInfoDocument
from stock_opportunity_agent.research.mining_agent_tools import project_facts_from_documents
P=ROOT/'runs/diagnostics/reviewed_gpre_capture_snapshot_20261021_v1/stage/snapshot/documents/0671.json'
sha=lambda b:hashlib.sha256(b).hexdigest()
before=P.read_bytes();d=RawInfoDocument.from_dict(json.loads(before));fs=project_facts_from_documents([d],case_ref='literal-audit-only');rows=[]
for fact in fs:
    r=json.loads(fact.exact_span)
    checks={'whole_literal_in_original':fact.exact_span in d.content,
        'value':fact.value==str(r['value']),'concept':fact.concept==r['tag'],
        'unit':fact.unit==r['unit'],'period':fact.period=={k:str(r[k]) for k in ('start','end') if r.get(k) is not None},
        'document_ref':fact.document_ref=='document-'+d.document_id,
        'source_content_hash':fact.content_hash==d.content_hash,
        'available_at':fact.available_at==d.available_at.isoformat(),
        'source_scope':fact.case_ref=='literal-audit-only'}
    rows.append({'fact':dataclasses.asdict(fact),'checks':checks,'whole_span_sha256':sha(fact.exact_span.encode())})
result={'source_file':str(P),'source_before_sha256':sha(before),'source_after_sha256':sha(P.read_bytes()),
    'expected_source_sha256':'ab081c728d390ce68c10d59336be1e8196ab1c4bb33c0febac2fdfb680347c31',
    'native_fact_count':len(fs),'all_checks_pass':all(all(x['checks'].values()) for x in rows),
    'facts':rows,'audit_script_sha256':sha(Path(__file__).read_bytes()),
    'scope':'One direct read-only native document projection; no model, Signal, network, research label or old-stage entry.'}
output=Path(__file__).with_name('candidate-original19-literal-audit.json');output.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
assert result['source_before_sha256']==result['source_after_sha256']==result['expected_source_sha256']
assert len(fs)==19 and result['all_checks_pass']
print(json.dumps({'facts':len(fs),'all_literal_identity_checks_pass':result['all_checks_pass'],'result_sha256':sha(output.read_bytes())}))
