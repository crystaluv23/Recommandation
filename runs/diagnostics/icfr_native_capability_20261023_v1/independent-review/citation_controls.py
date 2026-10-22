"""Independent old/current S4 readiness controls; synthetic, no role answers."""
from copy import deepcopy
from dataclasses import asdict
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import socket
import sys
from types import ModuleType, SimpleNamespace
from unittest.mock import patch

from stock_opportunity_agent.data.raw_info import RawInfoDocument, RawInfoStore
from stock_opportunity_agent.research.mining_controller import LabelAwareMiningController
from stock_opportunity_agent.research.signal_evolution import SignalEvolutionEngine

ROOT=Path(__file__).resolve().parent
REPO=ROOT.parents[3]
NOW=datetime(2025,1,1,tzinfo=timezone.utc)
old_module=ModuleType('independent_f9904bd5_mining_controller')
sys.modules[old_module.__name__]=old_module
old_source=ROOT/'old-f9904bd5-mining_controller.py.txt'
exec(compile(old_source.read_text(),str(old_source),'exec'),old_module.__dict__)
OLD=old_module.LabelAwareMiningController
FILES=['src/stock_opportunity_agent/research/mining_controller.py',
       'src/stock_opportunity_agent/research/mining_role_model.py',
       'src/stock_opportunity_agent/research/mining_agent_tools.py',
       'spec/src/stock_opportunity_agent/research/signal_mining_agent.md']


def bindings():
    return {p:hashlib.sha256((REPO/p).read_bytes()).hexdigest() for p in FILES}


def doc(name,company,body,source='company_news'):
    return RawInfoDocument.create(document_id=name,company_id=company,source_type=source,
        published_at=NOW,available_at=NOW,content=body)


def setup(cls,*,shared=False,samecase=False,hidden=False,whitespace=False):
    one=doc('source-one','issuer-one','Only a hypothetical ICFR risk, no actual management assessment.')
    company='issuer-one' if (shared or samecase) else 'issuer-two'
    two=one if shared else doc('source-two',company,
        '<script>HIDDEN_ONLY_TEXT</script><p>Dated management assessment found a material weakness.</p>'
        if hidden else ('   \n  Actual further narrative.' if whitespace else 'Dated management assessment found a material weakness.'),
        source='sec_filing' if hidden else 'company_news')
    companies=['issuer-one'] if samecase else ['issuer-one',company]
    cases=[SimpleNamespace(company_id=company,case_id='synthetic-'+str(i),prediction_time=NOW,
            ground_truth=SimpleNamespace(is_surge=False)) for i,company in enumerate(companies,1)]
    sink=[]
    c=cls(store=RawInfoStore(documents=[one] if shared else [one,two]),model=None,
        case_pairs=[('case-'+str(i).zfill(3),case) for i,case in enumerate(cases,1)],
        measurable_evidence_manifest={},signal_catalog=[],seed='discovery',
        label_map={'case-'+str(i).zfill(3):'control' for i in range(1,len(cases)+1)},
        validation_sink=lambda x:sink.append(deepcopy(x)) or {'status':'validated'})
    act(c,'fetch_evidence',case_refs=list(c.case_by_ref),source_families=['news']+(['filing'] if hidden else []),max_documents=3)
    first=next(e for e in c._events.values() if e.case_ref=='case-001' and e.document_ref=='document-source-one')
    second=next(e for e in c._events.values() if (e.case_ref==('case-001' if samecase else 'case-002')) and e.document_ref=='document-'+two.document_id)
    return c,sink,first,second


def act(c,name,**kwargs):
    raw=dict(action=name,rationale=['Independent synthetic access-lineage control.'],**kwargs)
    c._validate_action_shape(raw)
    return c._execute(name,raw)


def candidate(refs,families=None):
    return dict(measurement=dict(observable='independent_icfr_mechanical_control',value_kind='boolean',
        normalization='Explicit dated assessment under original object/time scope.',
        predicate=dict(modality='narrative',source_families=families or ['news'],
          semantic_condition='Management disclosed an actual dated ICFR material weakness.')),
        evidence_refs=refs,falsifiers=[dict(condition='Hypothetical risk only.',expected_observation='No established actual assessment.')])


def run(cls,scenario):
    c,sink,a,b=setup(cls,shared=scenario.startswith('shared'),samecase=scenario=='same-case-unrelated-doc',
                     hidden=scenario=='hidden-only',whitespace=scenario=='whitespace-only')
    act(c,'read_span',event_ref=a.event_ref,offset=0,length=100)
    refs=[b.event_ref];families=['filing'] if scenario=='hidden-only' else ['news']
    if scenario=='hidden-only':
        act(c,'read_span',event_ref=b.event_ref,offset=0,length=31)
    if scenario=='whitespace-only':
        act(c,'read_span',event_ref=b.event_ref,offset=0,length=6)
    if scenario=='mixed-read-and-unread':
        refs=[a.event_ref,b.event_ref]
    if scenario in ['matching-document','shared-matching-document']:
        act(c,'read_span',document_ref=b.document_ref,offset=0,length=100)
    if scenario=='matching-event':
        act(c,'read_span',event_ref=b.event_ref,offset=0,length=100)
    if scenario=='read-does-not-prove-meaning':
        refs=[a.event_ref] # A says hypothetical/no assessment; gate must not pretend semantics.
    before=(c._state,c._heavy_used,len(c.ledger.entries),len(sink))
    error=None
    try:
        status=act(c,'propose_candidate',candidate=candidate(refs,families))[0]
    except Exception as exc:
        status='rejected';error=type(exc).__name__+': '+str(exc)
    after=(c._state,c._heavy_used,len(c.ledger.entries),len(sink))
    exported=c.materialization_evidence()
    ready={ref:any(str(w.get('readable_text','')).strip() for w in exported.get(ref,{}).get('read_windows',[])) for ref in refs}
    return dict(status=status,error=error,before=before,after=after,sink_calls=len(sink),
                cited_refs=refs,export_ready=ready,ledger=[e.to_dict() for e in c.ledger.entries])


before=bindings();results=[]
scenarios=['unrelated-case','same-case-unrelated-doc','shared-other-case-event',
    'hidden-only','whitespace-only','mixed-read-and-unread','matching-document',
    'shared-matching-document','matching-event','read-does-not-prove-meaning']
with patch.object(socket,'create_connection',side_effect=AssertionError('network forbidden')),patch.object(socket.socket,'connect',side_effect=AssertionError('network forbidden')):
    for scenario in scenarios:
        old,new=run(OLD,scenario),run(LabelAwareMiningController,scenario)
        negative=scenario in scenarios[:6]
        assert old['status']=='candidate',(scenario,old)
        if negative:
            assert new['status']=='rejected' and 'executed readable window' in new['error'],(scenario,new)
            assert new['before']==new['after'] and new['sink_calls']==0,(scenario,new)
            assert not all(old['export_ready'].values()),(scenario,old)
        else:
            assert new['status']=='candidate' and all(new['export_ready'].values()),(scenario,new)
        results.append(dict(id=scenario,old=old,current=new,expected_new_rejection=negative,passed=True))
after=bindings();assert before==after
out=dict(old_commit='f9904bd5',old_controller_sha256=hashlib.sha256(old_source.read_bytes()).hexdigest(),
    current_bindings=before,stable_current_sources=True,results=results,
    boundary='Exact old controller source, same currently bound tools; synthetic observations; no semantic or production model acceptance',
    network=0,models=0,production_answers=0,check_or_locked_test=0)
(ROOT/'citation-results.json').write_text(json.dumps(out,indent=2)+'\n')
print(json.dumps(dict(controls=len(results),old_accepts_unready=6,current_rejects_unready=6,
    legal_positive_controls=3,semantic_countercontrol_accepted_as_access_only=True,stable_sources=True)))
