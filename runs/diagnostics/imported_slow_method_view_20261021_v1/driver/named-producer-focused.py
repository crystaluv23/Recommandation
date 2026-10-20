"""Native synthetic regression controls; no network or real label loading."""
import sys
sys.dont_write_bytecode=True
import difflib,hashlib,json,socket,ssl,time,unittest
from contextlib import ExitStack
from pathlib import Path
from unittest.mock import patch
from stock_opportunity_agent.cases.label_store import LabelStore
HERE=Path(__file__).resolve().parent; REPO=HERE.parents[3]
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
source=REPO/'src/stock_opportunity_agent/research/signal_evolution.py'
assert sha(source)=='23b036dfd4a116dba7518355210df66fefd5f880e69e03a9db63ae911bc4598f'
paths=[source,REPO/'tests/test_imported_slow_method_memory.py',REPO/'tests/scheme_evolution_test_support.py',REPO/'tests/test_signal_evolution_engine.py',REPO/'tests/test_imported_signal_feedback.py']
before={str(p):sha(p) for p in paths}; patchproof=[]
for filename in ('test_signal_evolution_engine.py','test_imported_signal_feedback.py'):
    old=(HERE/('before-named-producer-'+filename)).read_bytes();new=(REPO/'tests'/filename).read_bytes()
    oldlines=old.splitlines(keepends=True);newlines=new.splitlines(keepends=True)
    changes=[]
    for op,a,b,c,d in difflib.SequenceMatcher(a=oldlines,b=newlines,autojunk=False).get_opcodes():
        if op=='equal':continue
        assert op=='insert'
        assert all(line.strip()==b'metadata={"cik": "0000000001"},' for line in newlines[c:d])
        changes.extend([{'old_line':a+1,'new_line':n+1} for n in range(c,d)])
    patchproof.append({'file':filename,'before_sha256':hashlib.sha256(old).hexdigest(),'after_sha256':hashlib.sha256(new).hexdigest(),'added_metadata_lines':changes,'all_other_bytes_unchanged':True})
assert sum(len(p['added_metadata_lines']) for p in patchproof)==10
old=json.loads((HERE.parent/'root/original-failed-selectors-result.json').read_text())
selectors=[s for s in old['selectors'] if '.test_signal_evolution_engine.' in s]+['tests.test_imported_signal_feedback']
suite=unittest.defaultTestLoader.loadTestsFromNames(selectors);counts={'network':0,'label_store_load':0}
def deny(k):
    def call(*args,**kwargs):counts[k]+=1;raise AssertionError(k+' forbidden')
    return call
start=time.monotonic()
with (HERE/'named-producer-focused.log').open('x') as log,ExitStack() as stack:
    stack.enter_context(patch.object(socket,'socket',deny('network')))
    stack.enter_context(patch.object(socket,'create_connection',deny('network')))
    stack.enter_context(patch.object(LabelStore,'load',deny('label_store_load')))
    result=unittest.TextTestRunner(stream=log,verbosity=2).run(suite)
after={str(p):sha(p) for p in paths}
record={'tests':result.testsRun,'failures':[{'selector':t.id(),'traceback':tr} for t,tr in result.failures],'errors':[{'selector':t.id(),'traceback':tr} for t,tr in result.errors],'passed':result.wasSuccessful(),'selectors':selectors,'seconds':time.monotonic()-start,'tripwires':counts,'bindings_before':before,'bindings_after':after,'unchanged':before==after,'patch_proof':patchproof,'limitation':'Synthetic CIK1 binds normal test schema only; it does not establish real cross-issuer independence, fresh model obedience, source admission or research benefit.'}
with (HERE/'named-producer-focused-result.json').open('x') as f:json.dump(record,f,indent=2,sort_keys=True);f.write('\n')
print(json.dumps({k:record[k] for k in ('tests','passed','seconds','tripwires','unchanged')}))
raise SystemExit(0 if result.wasSuccessful() and before==after and not any(counts.values()) else 1)
