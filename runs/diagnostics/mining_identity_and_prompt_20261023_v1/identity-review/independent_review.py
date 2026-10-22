"""Independent offline identity boundary review; fixture answers are synthetic."""
import ast
import hashlib
import json
import re
from pathlib import Path
from typing import Any, Iterable, Mapping
from types import SimpleNamespace
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from unittest.mock import patch
from stock_opportunity_agent.models import ValidationError
from stock_opportunity_agent.llm import get_model
from stock_opportunity_agent.research.evolution_transport import (
    _CaseIdentityProjection, StructuredRoleClient, ExternalAttemptLedger,
    IdentityOutputRejected,
)
from stock_opportunity_agent.research.local_role_exchange import LocalRoleRequestPending
from stock_opportunity_agent.research.scheme_evolution import RuntimeBudgetExceeded
R = Path(__file__).resolve().parent
REPO = R.parents[3]
SOURCE = REPO / 'src/stock_opportunity_agent/research/evolution_transport.py'
F = json.loads((R / 'frozen-obligations.json').read_text())
CASES = F['cases'] + json.loads((R / 'frozen-obligations-supplement.json').read_text())['cases']
def sha(p): return hashlib.sha256(p.read_bytes()).hexdigest()
def write(name, value):
    with (R / name).open('x') as out: json.dump(value, out, indent=2, ensure_ascii=False)
def client(folder):
    folder.mkdir(parents=True, exist_ok=False)
    return StructuredRoleClient(registration=get_model('independent-subagent'),
        contract=SimpleNamespace(contract_hash='a'*64, limits={'max_structured_corrections':1,'max_local_role_calls':4}),
        workspace=folder, ledger=ExternalAttemptLedger(folder/'attempts.json',max_attempts=1,max_total_cost=1),
        allow_external=False,environ={})
def submit(c, pending, output):
    with Path(pending['outbox_path']).open('x') as out: json.dump(output,out,ensure_ascii=False)
    c.local_role_exchange.submit(pending['request_hash'],agent_id='/root/source_coordinate_review synthetic fixture; not a production author')
def run(name):
    before=sha(SOURCE)
    results=[]
    tree=ast.parse((R/'baseline-transport.py.txt').read_text())
    node=next(n for n in tree.body if isinstance(n,ast.ClassDef) and n.name=='_CaseIdentityProjection')
    ns=dict(re=re,Any=Any,Iterable=Iterable,Mapping=Mapping,ValidationError=ValidationError)
    exec(compile(ast.Module(body=[node],type_ignores=[]),'baseline-class','exec'),ns)
    for version,cls in [('baseline',ns['_CaseIdentityProjection']),('candidate',_CaseIdentityProjection)]:
        p=cls(F['aliases'],'cik_0001957939','CRML',expand_aliases=False)
        for case in CASES:
            view,inverse=p.project(case['text'])
            ok=(view==case['text'] if case['kind']=='preserve' else all(x not in view for x in case['forbidden']))
            results.append({'version':version,'case':case['id'],'pass':ok,'exact_inverse':p.restore(view,inverse)==case['text'],'view':view})
    p=_CaseIdentityProjection(F['aliases'],'cik_0001957939','CRML',expand_aliases=False)
    payload={'initial_research_skill':'Inspect only supplied evidence.', 'basic_info': {
        'document_ref':CASES[0]['text'], 'url':CASES[1]['text'], 'escaped_url':CASES[5]['text'],
        'cash':123456789012345678, 'snapshot_hash':'b'*64,
        'typed_patch':{'source_hash':'c'*64,'period':'2024-09-30','value':-2378789}}}
    canonical=json.dumps(payload,sort_keys=True)
    kwargs=dict(stage='research_controller_initialize',system_prompt='Copy supplied source coordinates only through supplied tokens.',payload=payload,allow_outcomes=False,max_output_tokens=800)
    root=R/name
    root.mkdir(exist_ok=False)
    native=client(root/'native')
    with native.anonymous_case(aliases=F['aliases'],company_id='cik_0001957939',ticker='CRML',expand_aliases=False):
        estimate=native.estimate_json_request_tokens(**{k:v for k,v in kwargs.items() if k!='stage'})
        try:native.complete_json(**kwargs)
        except LocalRoleRequestPending as exc: pending=exc.pending
        else:raise AssertionError('expected pending')
        inbox=json.loads(Path(pending['inbox_path']).read_text())
        messages=inbox['messages']; visible=json.loads(messages[1]['content'])
        reservation=len(json.dumps(messages,ensure_ascii=False,sort_keys=True,separators=(',',':')).encode())+inbox['max_output_tokens']
        requestfile=root/'native/requests'/f"{pending['request_hash']}.json"
        if not requestfile.exists(): requestfile=next((root/'native').rglob(pending['request_hash']+'.json'))
        canonical_request=json.loads(requestfile.read_text())
        expected_view,inverse=p.project({'system_prompt':kwargs['system_prompt'],'payload':payload})
        assert visible==expected_view['payload']
        assert estimate==reservation
        assert '0001213900-24-092156' not in json.dumps(messages)
        assert '000121390024092156' not in json.dumps(messages)
        assert visible['basic_info']['cash']==payload['basic_info']['cash']
        assert visible['basic_info']['typed_patch']==payload['basic_info']['typed_patch']
        assert p.restore(visible,inverse)==payload
        submit(native,pending,visible)
        output,usage=native.complete_json(**kwargs)
        assert output==payload and usage.tokens==reservation
        cached=list((root/'native/cache/responses').glob('*.json'))
        cache_hashes={str(x.relative_to(root)):sha(x) for x in cached}
        output2,usage2=native.complete_json(**kwargs)
        assert output2==payload and usage2.tokens==reservation
        assert cache_hashes=={str(x.relative_to(root)):sha(x) for x in cached}
        # Correction inputs pass through the identical boundary with original snapshots intact.
        correction={**kwargs,'stage':'research_controller_initialize_correction','payload':{**payload,'last_invalid_action':{'document_ref':CASES[0]['text']},'correction_feedback':['Copy the exact supplied coordinate token.']}}
        try:native.complete_json(**correction)
        except LocalRoleRequestPending as exc: cp=exc.pending
        else:raise AssertionError('expected correction pending')
        cv=json.loads(json.loads(Path(cp['inbox_path']).read_text())['messages'][1]['content'])
        assert '0001213900-24-092156' not in json.dumps(cv)
        assert cv['basic_info']['typed_patch']==payload['basic_info']['typed_patch']
    assert getattr(native._chain_state,'identity_projection',None) is None
    assert json.dumps(payload,sort_keys=True)==canonical
    # A too-small reservation rejects before inbox, without changing canonical payload.
    blocked=client(root/'budget-blocked')
    with blocked.anonymous_case(aliases=F['aliases'],company_id='cik_0001957939',expand_aliases=False):
        try:blocked.complete_json(**kwargs,max_request_tokens=estimate-1)
        except RuntimeBudgetExceeded:pass
        else:raise AssertionError('budget failed open')
    assert not list((root/'budget-blocked/local_roles/inbox').glob('*.json'))
    guard=[]
    for index,unsafe in enumerate(('0001213900-24-092156',CASES[1]['text'],'[ANON_ID_9876]')):
        c=client(root/f'guard-{index}')
        with c.anonymous_case(aliases=F['aliases'],company_id='cik_0001957939',expand_aliases=False):
            try:c.complete_json(**kwargs)
            except LocalRoleRequestPending as exc: pend=exc.pending
            av=json.loads(json.loads(Path(pend['inbox_path']).read_text())['messages'][1]['content'])
            submit(c,pend,{'unsafe':unsafe,'safe':av['basic_info']['document_ref']})
            try:c.complete_json(**kwargs)
            except IdentityOutputRejected as exc:
                guard.append({'unsafe':unsafe,'rejected':True,'quarantine':str(exc)})
            else:raise AssertionError('unsafe output accepted')
        # Independent direct quarantine verifies safe sibling restoration and exact violation path.
        v,t=p.project({'safe':CASES[0]['text']})
        quarantine,paths=p.quarantine_output({'unsafe':unsafe,'safe':v['safe']},t)
        assert quarantine['unsafe'] is None and quarantine['safe']==CASES[0]['text'] and paths==('unsafe',)
    # Nested/failure unwinding and worker isolation, including absent active-scope projection.
    assert native._request_identity_projection(()) is None
    try:
        with native.anonymous_case(aliases=('issuer A',),company_id='caseA'):
            first=native._request_identity_projection(())
            with native.anonymous_case(aliases=('issuer B',),company_id='caseB'):
                assert native._request_identity_projection(()) is not first
            assert native._request_identity_projection(()) is first
            raise RuntimeError('synthetic unwinding')
    except RuntimeError:pass
    assert native._request_identity_projection(()) is None
    barrier=Barrier(2)
    def worker(identity):
        with native.anonymous_case(aliases=(identity,),company_id=identity):
            barrier.wait(timeout=5)
            view,t=native._request_identity_projection(()).project(identity)
            assert view!=identity and native._request_identity_projection(()).restore(view,t)==identity
        return native._request_identity_projection(()) is None
    with ThreadPoolExecutor(max_workers=2) as pool: assert all(pool.map(worker,('issuer Alpha','issuer Beta')))
    oldreview=json.loads((REPO/'runs/diagnostics/mining_locator_generalization_20261023_v1/independent/final-query-and-budget-review.json').read_text())
    original_checks=[]
    for row in oldreview['budget_review']['requests']:
        source=Path(row['request']['path'])
        assert sha(source)==row['request']['sha256']
        data=json.loads(source.read_text())
        # Historical journals stay immutable; projected copy restores their exact historical bytes.
        messages=data['request']['messages']
        view,t=p.project(messages,allow_tokens=True)
        assert '0001213900-24-092156' not in json.dumps(view)
        original_checks.append({'path':str(source),'sha256':sha(source),'residual_projection_hidden':True})
    after=sha(SOURCE)
    assert before==after,'source changed during review'
    report={'source_sha256_before':before,'source_sha256_after':after,'counterexamples':results,'native':{'estimate':estimate,'reservation':reservation,'canonical_payload_unchanged':True,'messages_match_projected_payload':True,'cache_inverse_replay':True,'typed_snapshot_preserved':True,'correction_same_projection':True,'budget_rejected_before_inbox':True,'synthetic_fixture_only':True,'production_authors':0,'new_production_inboxes':0,'external_api_get':0},'output_guard':guard,'context_nested_failure_threads_isolated':True,'old_prepared_requests_unchanged':original_checks,'all_candidate_cases_pass':all(x['pass'] and x['exact_inverse'] for x in results if x['version']=='candidate'),'limitations':['Frozen cases were created after initial source candidate existed, before review execution.','Synthetic native fixtures establish wiring, not fresh model compliance or source truth.','No completed stage reentry; old aggregate budget failure and overall MVP remain.']}
    write(name+'-result.json',report)
    print(json.dumps({'artifact':name+'-result.json','all_candidate_cases_pass':report['all_candidate_cases_pass'],'source':before,'native_reservation':reservation}))
if __name__=='__main__':
    import sys
    with patch('socket.socket',side_effect=AssertionError('network forbidden')):
        run(sys.argv[1])
