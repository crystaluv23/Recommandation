"""Independent local native handoff/payload tests, with zero authored answers."""
from copy import deepcopy
from dataclasses import asdict
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
import hashlib
import json
import socket
import sys
import traceback

from freeze_controls import ROOT, REPO, NOW, action, case, controller, proposal
from stock_opportunity_agent.data.raw_info import RawInfoDocument
from stock_opportunity_agent.llm import get_model
from stock_opportunity_agent.models import ValidationError
from stock_opportunity_agent.research.evolution_core import EvolutionControlFlow
from stock_opportunity_agent.research.evolution_transport import StructuredRoleClient, ExternalAttemptLedger
from stock_opportunity_agent.research.local_role_exchange import LocalRoleRequestPending
from stock_opportunity_agent.research.mining_agent_tools import project_facts_from_documents
from stock_opportunity_agent.research.signal_evolution import SignalEvolutionEngine

OUT = ROOT / sys.argv[1]
OUT.mkdir(exist_ok=False)
RESULTS = []
BOUND = [REPO / 'src/stock_opportunity_agent/research' / p for p in
         ['mining_controller.py','signal_evolution.py','evolution_transport.py']]


def hashes():
    return {str(p.relative_to(REPO)):hashlib.sha256(p.read_bytes()).hexdigest() for p in BOUND}


def record(name, fn):
    try:
        detail = fn()
        RESULTS.append(dict(id=name, passed=True, detail=detail))
    except BaseException as exc:
        RESULTS.append(dict(id=name, passed=False, type=type(exc).__name__,
                            message=str(exc), traceback=traceback.format_exc()))


def source():
    p=REPO/'runs/diagnostics/reviewed_gpre_capture_snapshot_20261021_v1/stage/snapshot/documents/1179.json'
    return RawInfoDocument.from_dict(json.loads(p.read_text()))


def engine():
    e=object.__new__(SignalEvolutionEngine)
    e.slow_role_identity_guards=('IssuerPrivateName','0001951089','cik_0001951089','CRML')
    e.validator=SimpleNamespace(forbidden_identity_terms=e.slow_role_identity_guards,
                               deterministic_functions={})
    e.mining_model=SimpleNamespace(request_token_budget=200000)
    return e


def real_facts():
    d=source();c=controller([d]);action(c,'fetch_evidence',case_refs=['case-001'],source_families=['financial'],max_documents=1)
    facts=project_facts_from_documents([d],case_ref='case-001')
    fact=next(f for f in facts if f.concept=='EntityCommonStockSharesOutstanding')
    evidence=c.materialization_evidence()
    rows=SignalEvolutionEngine._controller_evidence_excerpts(proposal([fact.fact_ref]),evidence)
    row=rows[0]
    assert row['exact_span']==fact.exact_span
    assert json.loads(row['exact_span'])['value']==80994098
    assert row['taxonomy']=='dei' and row['content_hash']==d.content_hash and row['case_ref']=='case-001'
    assert row.get('document_source_type',row.get('source_type'))=='sec_company_facts', row
    wide=list(c._facts)[:13]
    assert len(SignalEvolutionEngine._controller_evidence_excerpts(proposal(wide),evidence))==13
    return dict(actual_span_chars=len(row['exact_span']), whole_rows=13)


def narrative():
    body='IssuerPrivateName front material. '*80+'TAIL_MILESTONE exact. '+'UNREAD_TRAILER '*80
    doc=RawInfoDocument.create(document_id='synthetic-doc',company_id='synthetic-company',
        source_type='company_news',published_at=NOW,available_at=NOW,content=body,
        metadata={'private':'DO_NOT_DISCLOSE_METADATA'})
    c=controller([doc],[case(doc.company_id,'one'),case(doc.company_id,'two')])
    action(c,'fetch_evidence',case_refs=['case-001','case-002'],source_families=['news'],max_documents=1)
    event=next(e for e in c._events.values() if e.case_ref=='case-001')
    docref='document-'+doc.document_id
    assert docref not in c.materialization_evidence()
    assert event.event_ref not in c.materialization_evidence(), 'unread discovery event promoted to source'
    start=body.index('TAIL_MILESTONE')
    action(c,'read_span',event_ref=event.event_ref,offset=start,length=21)
    one=deepcopy(c.materialization_evidence())
    assert next(e.event_ref for e in c._events.values() if e.case_ref=='case-002') not in one
    event_windows=one[event.event_ref]['read_windows']
    assert event_windows[0]['case_refs']==['case-001']
    assert event_windows[0]['readable_text']==body[start:start+21]
    assert event_windows[0]['target']=='event_ref' and event_windows[0]['ref']==event.event_ref
    assert 'UNREAD_TRAILER' not in json.dumps(one)
    assert 'DO_NOT_DISCLOSE_METADATA' not in json.dumps(one)
    action(c,'read_span',document_ref=docref,offset=start,length=21)
    action(c,'inspect_catalog',scope='signals')
    both=c.materialization_evidence()
    doc_windows=both[docref]['read_windows']
    assert len(doc_windows)==2 and {w['target'] for w in doc_windows}=={'event_ref','document_ref'}
    assert {tuple(w['case_refs']) for w in doc_windows}=={('case-001',),('case-001','case-002')}
    # A later fetch with a query changes discovery anchors, not actual reads.
    action(c,'fetch_evidence',case_refs=['case-001'],source_families=['news'],max_documents=1,query='front')
    final=c.materialization_evidence()
    assert final[event.event_ref]['read_windows']==both[event.event_ref]['read_windows']
    (OUT/'narrative-export.json').write_text(json.dumps(final,indent=2)+'\n')
    return c,doc,docref,event


def narrative_controls():
    c,doc,docref,event=narrative()
    return dict(raw_hash=doc.content_hash,windows=len(c.materialization_evidence()[docref]['read_windows']))


def relation():
    c=controller([source()]);action(c,'fetch_evidence',case_refs=['case-001'],source_families=['financial'],max_documents=1)
    r=next(iter(c._relations.values())); rows=SignalEvolutionEngine._controller_evidence_excerpts(proposal([r.relation_ref]),c.materialization_evidence())
    assert rows[0]['ref']==r.relation_ref
    assert [row['ref'] for row in rows[1:]]==list(r.fact_refs)
    assert all(row['exact_span']==c._facts[row['ref']].exact_span for row in rows[1:])
    assert all(row['content_hash']==source().content_hash for row in rows[1:])
    return dict(relation=r.relation_ref,ordered_operands=list(r.fact_refs))


def unknown():
    e=engine();failure={}
    class Never:
        def complete_json(self,**kwargs):
            raise AssertionError('materializer called before source prerequisite')
    value=e._materialize_controller_candidate(proposal(['unknown-ref']),caller=Never(),failures=failure,evidence={},seed='discovery')
    assert value is None and failure and 'source' in str(failure)
    return failure


def legacy():
    facts=project_facts_from_documents([source()],case_ref='case-001');f=facts[0]
    row=SignalEvolutionEngine._controller_evidence_excerpts(proposal([f.fact_ref]),{f.fact_ref:f})[0]
    assert row['exact_span']==f.exact_span and row['concept']==f.concept
    return dict(legacy_dataclass_fact=True)


def client(name):
    root=OUT/name
    return StructuredRoleClient(registration=get_model('independent-subagent'),
        contract=SimpleNamespace(contract_hash='b'*64,limits={'max_local_role_calls':3}),
        workspace=root,ledger=ExternalAttemptLedger(root/'unused-external.json',max_attempts=1,max_total_cost=.01),
        allow_external=False,environ={})


def native_capture():
    c,doc,docref,event=narrative();e=engine()
    candidate=proposal([docref],narrative=True); evidence=c.materialization_evidence()
    outputs=[]
    for module in ['spec','skill','tests']:
        caller=client('native-'+module)
        kwargs=dict(candidate=candidate,caller=caller,evidence=evidence,last_issues=[],accepted={'spec':{},'skill':'synthetic placeholder'})
        try:
            if module=='spec':
                kwargs['accepted']={};e._materialize_spec_module(**kwargs)
            elif module=='skill':
                kwargs['accepted']={'spec':{}};e._materialize_skill_module(**kwargs)
            else:
                e._materialize_tests_module(**kwargs,seed='discovery')
        except LocalRoleRequestPending as exc:
            inbox=json.loads(Path(exc.pending['inbox_path']).read_text())
            payload=json.loads(inbox['messages'][1]['content'])
            text=json.dumps(payload)
            assert 'TAIL_MILESTONE' in text and 'IssuerPrivateName' not in text
            assert 'UNREAD_TRAILER' not in text and 'DO_NOT_DISCLOSE_METADATA' not in text
            assert payload['cited_evidence']==e._masked_controller_evidence_excerpts(candidate,evidence)
            assert not list(caller.local_role_exchange.root.glob('outbox/*'))
            outputs.append(dict(module=module,request_hash=exc.pending['request_hash'],
                cited_evidence_count=len(payload['cited_evidence']),inbox=exc.pending['inbox_path']))
        else:
            raise AssertionError('expected pending native serializer, no answers permitted')
    return outputs


def native_real_fact_capture():
    d=source();c=controller([d]);action(c,'fetch_evidence',case_refs=['case-001'],source_families=['financial'],max_documents=1)
    fact=next(f for f in c._facts.values() if f.concept=='EntityCommonStockSharesOutstanding')
    candidate=proposal([fact.fact_ref]);evidence=c.materialization_evidence();e=engine()
    outputs=[]
    for module in ['spec','tests']:
        caller=client('native-real-'+module)
        try:
            if module=='spec':
                e._materialize_spec_module(candidate,caller=caller,evidence=evidence,last_issues=[],accepted={})
            else:
                e._materialize_tests_module(candidate,caller=caller,evidence=evidence,last_issues=[],accepted={'spec':{},'skill':None},seed='discovery')
        except LocalRoleRequestPending as exc:
            inbox=json.loads(Path(exc.pending['inbox_path']).read_text())
            payload=json.loads(inbox['messages'][1]['content'])
            row=payload['cited_evidence'][0]
            assert row['exact_span']==fact.exact_span and len(row['exact_span'])==692
            assert row['taxonomy']=='dei' and row['source_type']=='sec_company_facts'
            assert '0001951089' not in json.dumps(payload)
            assert json.loads(row['exact_span'])['value']==80994098
            outputs.append(dict(module=module,request_hash=exc.pending['request_hash'],span_chars=692))
        else:
            raise AssertionError('expected real-source pending serialization without answer')
    return outputs


def eof_markup_and_unknown_read():
    body='<html><script>HIDDEN_SECRET</script><body><p>Visible first paragraph.</p><p>TAIL_VISIBLE</p></body></html>'
    doc=RawInfoDocument.create(document_id='synthetic-markup',company_id='synthetic-company',
        source_type='sec_filing',published_at=NOW,available_at=NOW,content=body)
    c=controller([doc]);action(c,'fetch_evidence',case_refs=['case-001'],source_families=['filing'],max_documents=1)
    ref='document-'+doc.document_id;start=body.index('TAIL_VISIBLE')
    action(c,'read_span',document_ref=ref,offset=start,length=200)
    export=c.materialization_evidence()[ref]['read_windows'][0]
    assert export['length']==200 and export['raw_window_chars']==len(body)-start
    assert export['verbatim_hash']==hashlib.sha256(body[start:].encode()).hexdigest()
    assert export['readable_text']=='TAIL_VISIBLE'
    assert 'HIDDEN_SECRET' not in json.dumps(export)
    counts=(c._browse_used,len(c.ledger.entries)); before=deepcopy(c.materialization_evidence())
    assert c.materialization_evidence()==before and (c._browse_used,len(c.ledger.entries))==counts
    try:
        action(c,'read_span',document_ref='document-never-fetched',offset=0,length=10)
    except ValidationError:
        pass
    else:
        raise AssertionError('unknown document read accepted')
    assert c.materialization_evidence()==before
    return dict(requested_length=200,actual_raw_chars=export['raw_window_chars'],visible=export['readable_text'],read_budget_unchanged_by_export=True)


def budget():
    c,doc,docref,event=narrative();e=engine()
    native=client('native-budget')
    class ExplicitlyBoundedCaller:
        calls=0
        def complete_json(self,**kwargs):
            self.calls+=1
            kwargs['max_request_tokens']=10
            return native.complete_json(**kwargs)
    caller=ExplicitlyBoundedCaller()
    try:
        e._materialize_controller_candidate(proposal([docref],narrative=True),caller=caller,
            evidence=c.materialization_evidence(),failures={},seed='discovery')
    except EvolutionControlFlow as exc:
        assert not isinstance(exc,LocalRoleRequestPending), 'explicit caller cap did not stop before inbox'
        assert not list(native.local_role_exchange.root.glob('inbox/*'))
        assert caller.calls==1, 'resource stop entered content correction'
        return dict(type=type(exc).__name__,message=str(exc),inboxes=0,caller_calls=1,
                    cap_owner='explicit injected caller; no inferred H1/S5 cap')
    raise AssertionError('expected native budget control stop')


before=hashes()
with patch.object(socket,'create_connection',side_effect=AssertionError('network forbidden')),patch.object(socket.socket,'connect',side_effect=AssertionError('network forbidden')):
    for name,fn in [('actual-whole-fact-source-type-and-13refs',real_facts),
        ('read-window-case-lineage-no-unread-leak',narrative_controls),
        ('relation-ordered-operands',relation),('unknown-before-model',unknown),
        ('legacy-fact-object-helper',legacy),('native-spec-skill-tests-pending',native_capture),
        ('native-real-fact-spec-tests-pending',native_real_fact_capture),
        ('eof-markup-and-unknown-read',eof_markup_and_unknown_read),
        ('native-explicit-caller-budget-stop',budget)]:
        record(name,fn)
after=hashes()
(OUT/'results.json').write_text(json.dumps(dict(before=before,after=after,stable_sources=before==after,
    results=RESULTS,network_calls=0,model_calls=0,authored_answers=0,evidence='local deterministic controls and native pending request serialization only'),indent=2)+'\n')
print(json.dumps(dict(stable_sources=before==after,results=RESULTS),indent=2))
