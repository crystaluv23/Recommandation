"""One post-ready independent local run; all outputs stay in this new directory."""
from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import socket
import sys
import traceback
from types import ModuleType, SimpleNamespace
from unittest.mock import patch

from stock_opportunity_agent.data.raw_info import RawInfoDocument, RawInfoStore
from stock_opportunity_agent.llm import get_model
from stock_opportunity_agent.research.mining_controller import LabelAwareMiningController
from stock_opportunity_agent.research.mining_role_model import MiningAgentRoleModel, MiningRequestBudgetExhausted
from stock_opportunity_agent.research.evolution_transport import StructuredRoleClient, ExternalAttemptLedger
from stock_opportunity_agent.research.local_role_exchange import LocalRoleRequestPending

ROOT=Path(__file__).resolve().parent
REPO=ROOT.parents[3]
OUT=ROOT/sys.argv[1]
OUT.mkdir(exist_ok=False)
NOW=datetime(2025,1,1,tzinfo=timezone.utc)
SOURCES=json.loads((ROOT/'source-bindings-frozen.json').read_text())
CODE=['src/stock_opportunity_agent/research/mining_controller.py',
      'src/stock_opportunity_agent/research/mining_role_model.py',
      'src/stock_opportunity_agent/research/evolution_transport.py',
      'src/stock_opportunity_agent/research/mining_agent_tools.py',
      'spec/src/stock_opportunity_agent/research/signal_mining_agent.md']
RESULTS=[]
oldmod=ModuleType('independent_fixed10_old_narrative_controller')
sys.modules[oldmod.__name__]=oldmod
oldpath=ROOT/'old-mining_controller.py.txt'
exec(compile(oldpath.read_text(),str(oldpath),'exec'),oldmod.__dict__)
OLD=oldmod.LabelAwareMiningController


def sha(path): return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def nbytes(value): return len(json.dumps(value,ensure_ascii=False,sort_keys=True,separators=(',',':')).encode())
def dump(name,value): (OUT/(name+'.json')).write_text(json.dumps(value,indent=2,ensure_ascii=False)+'\n')
def bound(): return {p:sha(REPO/p) for p in CODE}
def frozen_unchanged():
    assert all(sha(path)==h for path,h in SOURCES['files'].items())
    return True
def record(name,fn):
    try: RESULTS.append(dict(id=name,passed=True,detail=fn()))
    except BaseException as e: RESULTS.append(dict(id=name,passed=False,error=str(e),type=type(e).__name__,traceback=traceback.format_exc()))
def case(company,ref,time=NOW):
    return SimpleNamespace(company_id=company,case_id='synthetic-'+ref,prediction_time=time,
                           ground_truth=SimpleNamespace(is_surge=False))
def document(name,body,company='synthetic-issuer',source='company_news',metadata=None):
    return RawInfoDocument.create(document_id=name,company_id=company,source_type=source,
        published_at=NOW,available_at=NOW,content=body,metadata=metadata or {})
def controller(docs,cls=LabelAwareMiningController,pairs=None,aliases=()):
    pairs=pairs or [('case-001',case(docs[0].company_id,'one'))]
    c=cls(store=RawInfoStore(documents=docs),model=None,case_pairs=pairs,
        measurable_evidence_manifest={},signal_catalog=[],seed='discovery',identity_aliases=aliases,
        label_map={ref:'control' for ref,_ in pairs})
    act(c,'fetch_evidence',case_refs=[ref for ref,_ in pairs],
        source_families=sorted({d.source_type for d in docs}),max_documents=len(docs))
    return c
def act(c,name,**kw):
    value=dict(action=name,rationale=['Independent synthetic source-view control.'],**kw)
    c._validate_action_shape(value)
    return c._execute(name,value)
def read(c,d,offset=0,length=100,target=None):
    kw=target or {'document_ref':'document-'+d.document_id}
    return act(c,'read_span',**kw,offset=offset,length=length)
def page(c):
    view=c._model_view(); assert 'narrative_read_evidence' in view
    p=view['narrative_read_evidence'];assert len(p['items'])<=12 and nbytes(p['items'])<=40000
    assert p['revisit_action'] and 'read_span' in json.dumps(p['revisit_action'])
    return p
def state(c): return (c._heavy_used,c._light_used,c._browse_used,c.ledger.to_dict(),deepcopy(c.materialization_evidence()))


def actual_fixed10():
    frozen_unchanged();docs=[];pairs=[]
    for row in SOURCES['actual_sources']:
        d=RawInfoDocument.from_dict(json.loads(Path(row['path']).read_text()));docs.append(d)
        pairs.append((row['case_ref'],case(d.company_id,row['case_ref'],datetime.fromisoformat(row['cutoff']))))
    a=next(d for d in docs if d.content_hash=='f6bbe6a78628f1e9e452e03b03dd55cbb6afe56291fe2284237ea4aecefa2766')
    b=next(d for d in docs if d.content_hash=='8de6937582d3f2b985c7cb3c6ce206a4cc38fa0b8729f7105f56fe373bc2bfa7')
    instances=[]
    for cls in [OLD,LabelAwareMiningController]:
        c=controller(docs,cls,pairs)
        read(c,a,1148801,4000);read(c,a,1152908,4000)
        act(c,'inspect_catalog',scope='evidence')
        read(c,b,3969625,4000)
        instances.append(c)
    old,new=instances
    assert state(old)==state(new), 'runtime S5/ledger/budgets changed'
    oldv,newv=old._model_view(),new._model_view()
    assert 'narrative_read_evidence' not in oldv
    before=state(new);p=page(new);assert len(p['items'])==3
    expected={(w['content_hash'],w['offset'],w['length']):w['readable_text']
        for unit in new.materialization_evidence().values() if unit.get('evidence_kind')=='document_read'
        for w in unit['read_windows']}
    assert {(x['content_hash'],x['offset'],x['length']):x['readable_text'] for x in p['items']}==expected
    assert 'There were no changes in our internal control' not in json.dumps(oldv)
    assert page(new)==p and state(new)==before
    dump('actual-new-view',newv);dump('actual-old-view',oldv)
    frozen_unchanged()
    return dict(actual_source_windows=3,old_only_latest_body=True,new_all_three_together=True,
                runtime_materialization_and_read_ledger_equal=True,budgets_equal=True)


def max_unicode():
    a=document('unicode-A','𠀀'*3999+'A')
    b=document('unicode-B','🧠'*3999+'B')
    c=controller([a,b]);read(c,a,0,4000);read(c,b,0,4000)
    p=page(c);assert len(p['items'])==2
    assert {x['readable_text'] for x in p['items']}=={a.content,b.content}
    assert all(len(x['readable_text'])==4000 for x in p['items'])
    dump('max-unicode-page',p)
    return dict(full_unicode_windows=2,whole_items_json_bytes=nbytes(p['items']))


def whole_page_and_reread():
    body=''.join((f'WINDOW_{i:02d} complete exact source.').ljust(100,' ') for i in range(13))
    d=document('thirteen-ranges',body);c=controller([d])
    observed={}
    for i in range(13):
        read(c,d,i*100,40)
        observed[i*100]=c._last_action_result['masked']
    p=page(c);assert p['counts']['available']==13 and len(p['items'])==12
    assert [x['offset'] for x in p['items']]==[i*100 for i in reversed(range(1,13))]
    omitted=p['omitted_entries'];assert any(x['offset']==0 and x['required_bytes']>0 for x in omitted)
    before=c._browse_used;read(c,d,0,40);q=page(c)
    assert q['items'][0]['offset']==0 and q['items'][0]['read_count']==2
    assert c._browse_used==before+1 and q['counts']['available']==13 and len(q['items'])==12
    # The baseline is the complete readable/masked text actually disclosed by
    # each original read, not raw padding removed by the existing projection.
    assert all(x['readable_text']==observed[x['offset']] for x in q['items'])
    dump('whole-page-before-reread',p);dump('whole-page-after-reread',q)
    return dict(available_units=13,included_units=12,whole_omission_disclosed=True,reread_browse_charge=1)


def case_and_target_scope():
    d=document('shared-source','A dated disclosed observation. UNREAD_LATER_SECRET')
    pairs=[('case-001',case(d.company_id,'one')),('case-002',case(d.company_id,'two'))]
    c=controller([d],pairs=pairs)
    event=next(e for e in c._events.values() if e.case_ref=='case-001')
    other=next(e for e in c._events.values() if e.case_ref=='case-002')
    read(c,d,0,29,target={'event_ref':event.event_ref});p=page(c)
    assert len(p['items'])==1 and p['items'][0]['case_refs']==['case-001']
    assert p['items'][0]['read_targets']==[{'target':'event_ref','ref':event.event_ref,'case_refs':['case-001']}]
    assert other.event_ref not in c.materialization_evidence()
    read(c,d,0,29);q=page(c);assert len(q['items'])==1
    assert q['items'][0]['case_refs']==['case-001','case-002']
    targets=q['items'][0]['read_targets']
    assert any(x['target']=='document_ref' and x['case_refs']==['case-001','case-002'] for x in targets)
    assert all(x['ref']!=other.event_ref for x in targets)
    assert 'UNREAD_LATER_SECRET' not in json.dumps(q)
    dump('case-target-page',q)
    return dict(shared_raw_unit_coalesced=True,only_executed_target_case_scopes=True)


def hidden_and_metadata():
    d=document('markup-source','<script>HIDDEN_SECRET</script><p>READABLE_ACTUAL_WINDOW</p><p>UNREAD_BODY_SECRET</p>',
               source='sec_filing',metadata={'private_key':'UNREAD_METADATA_SECRET'})
    c=controller([d]);read(c,d,0,28);p=page(c)
    assert 'HIDDEN_SECRET' not in json.dumps(p) and 'UNREAD_BODY_SECRET' not in json.dumps(p)
    start=d.content.index('READABLE_ACTUAL_WINDOW');read(c,d,start,len('READABLE_ACTUAL_WINDOW'));q=page(c)
    text=json.dumps(q)
    assert 'READABLE_ACTUAL_WINDOW' in text
    assert not any(s in text for s in ['HIDDEN_SECRET','UNREAD_BODY_SECRET','UNREAD_METADATA_SECRET'])
    return dict(hidden_and_unread_absent=True,actual_visible_body_present=True)


def oversized_whole_unit():
    # Force a supported source-unit size boundary via a valid synthetic long
    # opaque handle; ordinary maximum Unicode windows are tested separately.
    d=document('oversized-'+('x'*41000),'Actual short readable body.')
    c=controller([d]);read(c,d,0,27);p=page(c)
    assert not p['items'] and p['counts']['oversized']>=1
    rows=p['oversized_entries'];assert any(x['offset']==0 and x['length']==27 and x['required_bytes']>40000 and x['content_hash']==d.content_hash for x in rows)
    assert 'Actual short readable body.' not in json.dumps(rows)
    dump('oversized-disclosure',p)
    return dict(body_not_clipped_or_included=True,required_bytes_disclosed=rows[0]['required_bytes'])


def deterministic_reconstruction():
    d=document('reconstruct','FIRST_MEANING '+('x'*90)+' SECOND_MEANING')
    views=[];states=[]
    for _ in range(2):
        c=controller([d]);read(c,d,0,14);read(c,d,104,16)
        act(c,'inspect_catalog',scope='signals')
        views.append(c._model_view());states.append(state(c))
    assert views[0]==views[1] and states[0]==states[1]
    return dict(same_accepted_actions_same_complete_view=True,model_calls=0)


def native_wire_identity_cost():
    alias='IssuerPrivateName';company='cik_0000012345'
    d=document('sec:'+company+':filing:stable',alias+' FIRST_READ_MEANING '+('x'*100)+' '+alias+' SECOND_READ_MEANING',company=company)
    c=controller([d],aliases=(alias,company,'0000012345'))
    read(c,d,0,38);start=d.content.index(alias,40);read(c,d,start,len(d.content)-start)
    act(c,'inspect_catalog',scope='signals');view=c._model_view();p=page(c)
    root=OUT/'native-wire'
    caller=StructuredRoleClient(registration=get_model('independent-subagent'),
        contract=SimpleNamespace(contract_hash='b'*64,limits={'max_local_role_calls':3}),workspace=root,
        ledger=ExternalAttemptLedger(root/'unused-external.json',max_attempts=1,max_total_cost=.01),
        allow_external=False,environ={})
    model=MiningAgentRoleModel(caller,identity_aliases=(alias,company,'0000012345'),
        max_request_tokens=262144,max_total_tokens=1048576,max_calls=3,max_output_tokens=2000)
    try:model.next_action(view)
    except LocalRoleRequestPending as exc:pending=exc.pending
    else:raise AssertionError('native pending input expected')
    inbox=json.loads(Path(pending['inbox_path']).read_text())
    wire=json.loads(next(m['content'] for m in inbox['messages'] if m['role']=='user'))
    raw=json.dumps(inbox)
    assert alias not in raw and company not in raw and '0000012345' not in raw
    assert 'FIRST_READ_MEANING' in raw and 'SECOND_READ_MEANING' in raw
    reservation=nbytes(inbox['messages'])+inbox['max_output_tokens']
    assert int(wire['request_budget']['this_request'])==reservation
    target=wire['narrative_read_evidence']['items'][0]['document_ref']
    response={'action':'read_span','document_ref':target,'offset':0,'length':38,
              'rationale':['Explicit synthetic local transport fixture; not a production role answer.']}
    Path(pending['outbox_path']).write_text(json.dumps(response))
    caller.local_role_exchange.submit(pending['request_hash'],agent_id='synthetic-independent-identity-control-not-production-actor')
    restored=model.next_action(view)
    assert restored['document_ref']=='document-'+d.document_id
    assert model.reserved_tokens==reservation and model.reserved_calls==1
    # A new explicit tiny request limit rejects before preparing an inbox.
    tiny=MiningAgentRoleModel(caller,max_request_tokens=1,max_output_tokens=2000)
    before=len(list(caller.local_role_exchange.root.glob('inbox/*.json')))
    try:tiny.next_action(view)
    except MiningRequestBudgetExhausted:pass
    else:raise AssertionError('tiny budget did not stop')
    assert len(list(caller.local_role_exchange.root.glob('inbox/*.json')))==before
    return dict(native_full_read_units=2,request_hash=pending['request_hash'],exact_wire_reservation=reservation,
                synthetic_action_handle_restored=True,small_existing_budget_rejected_before_inbox=True,
                actual_production_role_answers=0,synthetic_local_answers=1)


before=bound();assert frozen_unchanged()
with patch.object(socket,'create_connection',side_effect=AssertionError('network forbidden')),patch.object(socket.socket,'connect',side_effect=AssertionError('network forbidden')):
    for name,fn in [('actual-fixed10-new-vs-old',actual_fixed10),('two-maximum-unicode-windows',max_unicode),
        ('whole-page-omission-and-charged-reread',whole_page_and_reread),('case-target-scope',case_and_target_scope),
        ('hidden-unread-metadata',hidden_and_metadata),('oversized-whole-unit',oversized_whole_unit),
        ('deterministic-reconstruction',deterministic_reconstruction),('native-wire-identity-reverse-cost',native_wire_identity_cost)]:
        record(name,fn)
after=bound();assert frozen_unchanged()
dump('results',dict(before=before,after=after,stable_sources=before==after,results=RESULTS,
    scope='Local source/input and synthetic boundary controls only; not fresh Mining or semantic/admission/reuse/MVP evidence',
    network=0,external_API=0,production_actor_dispatch=0,production_answers=0))
print(json.dumps(dict(stable_sources=before==after,results=RESULTS),indent=2))
