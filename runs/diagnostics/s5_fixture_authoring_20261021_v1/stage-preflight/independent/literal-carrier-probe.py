"""Offline native stage under temporary fixed roots; no real stage or model."""
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
from copy import deepcopy
import json,hashlib
from scripts import run_reviewed_fixture_author_stage as s
R=Path('/Users/l/Project/Recommandation');O=R/'runs/diagnostics/s5_fixture_authoring_20261021_v1/stage-preflight/independent';sha=lambda p:hashlib.sha256(Path(p).read_bytes()).hexdigest()
assert sha(s.__file__)=='770715c059840387eb334e95a97bd11b69910f113e4edee3369eb9e4f7943878'
inputs=s._inputs();fixtures=[]
for schema in ['legacy','typed']:
 facts=[json.loads(x['exact_span']) for x in inputs['evidence'].values() if x.get('title')==schema+' SEC fact row']
 body={'cik':1,'facts':{'us-gaap':{'Revenues':{'units':{'USD':facts}}}}} if schema=='legacy' else {'schema_version':'sec-company-facts-document-v1','cik':1,'filing_date':'2025-02-15','form':'10-K','facts':facts}
 fixtures.append({'name':'independent '+schema,'expected':'positive','as_of':s.CUTOFF,'documents':[{'document_id':'independent-'+schema,'source_type':'financials','published_at':s.AVAILABLE,'available_at':s.AVAILABLE,'metadata':{'cik':1},'content':json.dumps(body,sort_keys=True,separators=(',',':'))}]})
answers={'positive':{'tests':fixtures}};bad=deepcopy(fixtures);body=json.loads(bad[1]['documents'][0]['content']);body['nonfact_literal_copies']=deepcopy(body['facts'])
for row in body['facts']:row.pop('filed');row.pop('form')
bad[1]['documents'][0]['content']=json.dumps(body,sort_keys=True,separators=(',',':'));answers['typed_actual_rows_not_copied_but_dead_literal_objects_present']={'tests':bad};rows=[]
for name,answer in answers.items():
 with TemporaryDirectory(prefix='independent-S5-stage-literal-') as tmp:
  root=Path(tmp)/'stage'
  with patch.object(s,'STAGE_ROOT',root):
   s.prepare(root);pending=s.resume(root);assert pending['status']=='pending_independent_role';inbox=pending['pending'];out=Path(inbox['outbox_path']);text=json.dumps(answer,separators=(',',':'));out.write_text(text);s.submit(root,inbox['request_hash'],'offline-independent-fixture-only');result=s.resume(root)
   loaded=s.read(root/'loaded-candidate.json') if (root/'loaded-candidate.json').exists() else None
   rows.append({'name':name,'result':result,'authored_answer':answer,'loaded_schemas':loaded and loaded['schemas'],'measurements':loaded and [x['measurement'] for x in loaded['results']],'actual_pending_payload':json.loads(s.read(inbox['inbox_path'])['messages'][1]['content']) if 'inbox_path' in inbox else None})
   print(name,result['status'])
report={'source_sha':sha(s.__file__),'rows':rows,'scope':'temporary native prepare/pending/exact raw/submit/resume only; offline authored fixtures, no real formal root/model/network/labels'}
p=O/'literal-carrier-results.json';p.write_text(json.dumps(report,indent=2)+'\n');print('RESULT',hashlib.sha256(p.read_bytes()).hexdigest())
