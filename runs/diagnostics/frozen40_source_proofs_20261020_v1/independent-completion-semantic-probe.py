"""Temp-only body-carrier counterexample, usable with preserved or current reader."""
from copy import deepcopy
import importlib.machinery,importlib.util,json,sys
from pathlib import Path
from unittest.mock import patch
import tests.test_frozen_source_completion as fixtures
path=Path(sys.argv[1]) if len(sys.argv)>1 else Path(__file__).with_name('completion-consumer-original-reader.py.txt')
loader=importlib.machinery.SourceFileLoader('independent_completion_consumer',str(path));spec=importlib.util.spec_from_loader(loader.name,loader);reader=importlib.util.module_from_spec(spec);loader.exec_module(reader)
checks=[]
with patch.object(fixtures,'completion',reader):
 t=fixtures.FrozenSourceCompletionTests();t.setUp()
 try:
  assert len(t.qualify())==1
  checks.append({'name':'body_raw_positive','accepted':True})
  for proof in t.candidate['proofs']:
   if proof['kind']=='sec_static_archive_body_response':continue
   review=deepcopy(t.semantic);review['records'][0]['body_binding']=proof['artifact']
   candidate={**t.candidate,'semantic_review':fixtures.write(t.base/'wrong-carrier.json',review)}
   try:accepted=len(t.qualify([candidate]))==1;error=None
   except reader.ReviewedSourceRejected as e:accepted=False;error=str(e)
   checks.append({'name':'wrong_'+proof['kind']+'_artifact_as_semantic_body','accepted':accepted,'error':error})
 finally:t.doCleanups()
print(json.dumps({'reader':str(path),'checks':checks}))
