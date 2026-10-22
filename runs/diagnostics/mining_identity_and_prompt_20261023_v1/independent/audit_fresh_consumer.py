"""Read-only audit of sealed fresh Mining controls; never advances a stage."""
import json,hashlib,re
from pathlib import Path
from decimal import Decimal
from stock_opportunity_agent.artifacts import canonical_json_hash
from stock_opportunity_agent.research.evolution_transport import _CaseIdentityProjection
from stock_opportunity_agent.research.evolution_core import _assert_identity_values_masked
R=Path(__file__).resolve().parent
REPO=R.parents[3]
B=REPO/'runs/diagnostics/mining_locator_generalization_20261023_v1'
ST=B/'stage'
def read(p):return json.loads(p.read_text())
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def binding(p):return {'path':str(p),'sha256':sha(p)}
def check(x):assert sha(Path(x['path']))==x['sha256'],x['path']
def matching_keys(x,path=''):
    out=[]
    if isinstance(x,dict):
        for k,v in x.items():
            p=path+'/'+k
            if re.search('token|cost|reservation|llm|remaining|limit',k,re.I):out.append({'path':p,'value':v if not isinstance(v,(dict,list)) else type(v).__name__})
            out+=matching_keys(v,p)
    elif isinstance(x,list):
        for i,v in enumerate(x):out+=matching_keys(v,path+'/'+str(i))
    return out

def audit(key,inputs,reference):
    folder=ST/key
    terminal_path=next((p for p in (folder/'completion.json',folder/'failure.json')if p.exists()),None)
    assert terminal_path is not None,'wait for sealed terminal'
    terminal=read(terminal_path)
    assert terminal['terminal_hash']==canonical_json_hash({k:v for k,v in terminal.items()if k!='terminal_hash'})
    for row in terminal['sealed_files']:check(row)
    sample=inputs[key]; src=next(x for x in reference['samples']if x['case_ref']==sample['case_ref']);check(src['source_file'])
    source=read(Path(src['source_file']['path']));content=source['content'];body=json.loads(content)
    p=_CaseIdentityProjection((sample['case_id'],sample['company_id']),'','',expand_aliases=False)
    requestfiles=list((folder/'requests').glob('*.json'))
    rawrequests={x:read(x)for x in requestfiles}
    matched=set();steps=[];answered=0;blocked=0;answer_reservation=0;corrections=0;allres=0
    for index,vpath in enumerate(sorted(folder.glob('view-*.json')),1):
        view=read(vpath);projected,inverse=p.project({'system_prompt':'','payload':view})
        hits=[x for x,d in rawrequests.items()if json.loads(d['request']['messages'][1]['content'])==projected['payload']]
        assert len(hits)==1,'view must match one actual native request'
        path=hits[0];matched.add(path);record=rawrequests[path];req=record['request'];digest=record['request_hash']
        assert canonical_json_hash(req)==digest==path.stem
        assert p.restore(projected['payload'],inverse)==view
        messages=req['messages'];_assert_identity_values_masked(messages,(sample['case_id'],sample['company_id']))
        wire=json.dumps(messages,ensure_ascii=False)
        assert not re.search(r'(?<![A-Za-z0-9])\d{10}-\d{2}-\d{6}(?![A-Za-z0-9])',wire)
        assert src['document_outer_except_content']['metadata']['accession_number'] not in wire
        reserve=len(json.dumps(messages,ensure_ascii=False,sort_keys=True,separators=(',',':')).encode())+req['max_output_tokens']
        assert req['max_output_tokens']==2000 and reserve<=32768
        allres+=reserve
        inbox=folder/'exchange/inbox'/path.name;receipt=folder/'exchange/receipts'/path.name;raw=folder/'exchange/outbox'/(digest+'.txt');cache=folder/'cache/responses'/path.name
        step={'step':index,'request':binding(path),'reservation':reserve,'visible_budget':view['budget'],'read_receipts':len(view.get('structured_read_progress',{}).get('items',[])),'canonical_projection_and_inverse_exact':True,'known_alias_and_explicit_sourcecoordinate_residuals':0,'budget_related_fields':matching_keys(projected['payload'])}
        system=messages[0]['content']
        step['system_discloses_native_call_budget']=bool(re.search(r'98304|32768|max_case_tokens|max_request_tokens|request.?reservation|remaining case|cumulative.*(?:token|byte)|endpoint.*reserve',system,re.I))
        if inbox.exists():
            answered+=1;answer_reservation+=reserve
            ib=read(inbox);rc=read(receipt);cc=read(cache);rawtext=raw.read_text();parsed=json.loads(rawtext)
            assert ib['request_hash']==digest and ib['messages']==messages
            assert rc['request_hash']==digest and rc['inbox_sha256']==sha(inbox) and rc['raw_output_sha256']==sha(raw)
            assert cc['request_hash']==digest and cc['raw_output']==rawtext and cc['json_output']==parsed
            assert cc['usage']['accounting_tokens']==reserve
            action=read(folder/f'action-{index:03}.json')
            assert p.restore(parsed,inverse)==action
            iscorrection=bool(view.get('last_invalid_action'));corrections+=iscorrection
            step.update({'status':'answered_correction'if iscorrection else'answered_first','inbox':binding(inbox),'raw':binding(raw),'receipt':binding(receipt),'cache':binding(cache),'agent_id':rc['agent_id'],'action':action,'cache_raw_parsed_action_exact':True})
            if action['action']=='read_span':assert action['fact_ref']in view['known_fact_refs']
            if action['action']=='compute_statistic':
                assert action['action']in view['available_actions'] and view['budget']['heavy_remaining']>0
                assert len(action['fact_refs'])==2
        else:
            blocked+=1
            assert not receipt.exists()and not raw.exists()and not cache.exists()
            step.update({'status':'blocked_before_inbox','author':None,'not_a_semantic_response':True})
        steps.append(step)
    assert matched==set(requestfiles)
    endpoint=terminal_path.name=='completion.json'
    if endpoint:
        boundary=read(folder/'boundary.json');assert boundary['native_domain_terminal_executed']is False
        assert boundary['assembled_intent']==steps[-1]['action']and steps[-1]['action']['action']=='record_deferred'
        finalview=boundary['view'];ledger=boundary['ledger'];assert not any(x.get('terminal_disposition')for x in ledger['entries'])
    else:
        failed=read(folder/'failed-controller.json');finalview=failed['view'];ledger=failed['ledger']
        assert not (folder/'boundary.json').exists()
    receipts=finalview.get('structured_read_progress',{}).get('items',[])
    assert len(receipts)==2 and finalview['structured_read_progress']['selection_is_exhaustive']
    sourceproof=[]
    for receipt_row in receipts:
        fact=receipt_row['fact']
        oracle=next(x for x in src['operands_in_original_order']if str(x['whole_row']['value'])==fact['value'])
        exact=body['facts'][int(oracle['source_json_pointer'].split('/')[-1])];assert exact==oracle['whole_row']
        assert fact=={'concept':exact['tag'],'period':{'start':exact['start'],'end':exact['end']},'taxonomy':exact['taxonomy'],'unit':exact['unit'],'value':str(exact['value'])}
        assert receipt_row['masked']in content and json.dumps(exact,ensure_ascii=False,sort_keys=True,separators=(',',':'))in receipt_row['masked']
        assert receipt_row['content_hash']==hashlib.sha256(content.encode()).hexdigest()
        sourceproof.append({'fact_ref':receipt_row['fact_ref'],'whole_row':exact,'source_pointer':oracle['source_json_pointer'],'exact_quote_and_hash':True})
    readentries=[x for x in ledger['entries']if x['action']=='read_span']
    assert len(readentries)==2
    if any(s.get('action',{}).get('action')=='compute_statistic'for s in steps):
        math=finalview['last_action_result'];exactlatest=max(sourceproof,key=lambda x:x['whole_row']['end'])['whole_row'];prior=min(sourceproof,key=lambda x:x['whole_row']['end'])['whole_row'];expected=Decimal(str(exactlatest['value']))-Decimal(str(prior['value']))
        assert math['rule']=='latest_minus_comparable_prior'and Decimal(math['value'])==expected
    else:math=None
    assert answer_reservation<=98304
    for row in terminal['sealed_files']:check(row)
    return {'sample':key,'terminal':binding(terminal_path),'terminal_state':terminal['state'],'sealed_files_verified':len(terminal['sealed_files']),'steps':steps,'prepared_requests':len(requestfiles),'answered_first':answered-corrections,'answered_corrections':corrections,'blocked_before_inbox':blocked,'answered_reservation':answer_reservation,'blocked_reservation':allres-answer_reservation,'all_prepared_reservation':allres,'original_ceiling':98304,'headroom_after_answers':98304-answer_reservation,'module_endpoint_produced':endpoint,'final_intent':steps[-1].get('action')if endpoint else None,'actual_final_compute_result':math,'actual_ledger_actions':[x['action']for x in ledger['entries']],'source_operands':sourceproof,'source_reference':src['source_file'],'O1':'pass:bothsourceoperandreadsreallyexecuted','O2':'materialsourcebindingsandlegalarithmeticexact;seeindependentproserationaleassessment','O3':'finalintentavailable:reviewrationale'if endpoint else'notreached:no finalintent;fourthcompute rationale is not finalintent','O4':'pass:whole2receiptsretainedandcomparisonlocatorscurrentinlateractualwire','O5':'pass:assembledrecord_deferredinterceptedbefore nativeterminal'if endpoint else'fail:budgetblockedbeforeendpointauthor','O6':{'limits_enforced':True,'original_samples_and_denominator':True,'no_correction_budget_reset':True,'inbudget_module_endpoint':endpoint},'scope_limit':'Historical normalized one-selected-document inspection; no candidate/admission/publication/reuse/independentgain claim.'}

def main():
    manifest=read(ST/'manifest.json');body={k:v for k,v in manifest.items()if k!='manifest_hash'};assert canonical_json_hash(body)==manifest['manifest_hash']
    inputs=read(ST/'inputs.json');contract=read(ST/'contract.json');assert canonical_json_hash(inputs)==manifest['inputs_hash']and canonical_json_hash(contract)==manifest['contract_hash']
    for x in manifest['source_files']+manifest['code_files']:check(x)
    reference=read(B/'reference/source-reference.json');results=[audit(k,inputs,reference)for k in('a','b')]
    old=read(B/'independent/final-query-and-budget-review.json')
    for x in old['budget_review']['requests']:check(x['request'])
    check(old['budget_review']['record'])
    for x in old['old_stage_preservation']['terminals']:
        check(x['terminal']);t=read(Path(x['terminal']['path']))
        for y in t['sealed_files']:check(y)
    for x in manifest['source_files']+manifest['code_files']:check(x)
    out={'schema_version':'independent-fresh-mining-consumer-review-v1','manifest':binding(ST/'manifest.json'),'fixed_denominator':2,'module_endpoint_count':sum(x['module_endpoint_produced']for x in results),'samples':results,'formal_fresh_authors':sum(x['answered_first']+x['answered_corrections']for x in results),'corrections':sum(x['answered_corrections']for x in results),'blocked_prepared_without_inbox':sum(x['blocked_before_inbox']for x in results),'source_bindings_verified':len(manifest['source_files']),'code_bindings_verified':len(manifest['code_files']),'old_failure_102563_and_fourprepared_preserved':True,'old0671_namespace_terminal_and_sealedchildren_preserved':True,'budget_observability':'Actual native userbudget exposes onlyheavy/browse/light; memory/catalogbytelimitsunrelated. System has no98304aggregate/32768single/callreservation/consumedtotal/endpointreserve. Thereforeauthorcannotinferoptionallegalcomputeaffordability;fourstep preflight is reachability,not a requirement forallvalidpaths.','classification':'Budget-enforced module endpoint failure is separatefrom source-reading/measurement/arithmetic semantic success. Do not blame optionalcompute or inventmissingterminalrationale.','zero_counts':{'external_api_get':0,'new_businesslabels':0,'candidates_publications':0,'completed_stage_reentry_by_reviewer':0},'reviewer_writes':'Only newglobaldiag independent artifacts; frozenBASE/reference/product/oldoriginals unchanged.','remaining':'Final rationale semantics are independently stated in accompanying source-semantic-supplement; wholeMVP/S3S4/forecastbenefit remainopen.'}
    with(R/'fresh-consumer-mechanical-review.json').open('x')as f:json.dump(out,f,ensure_ascii=False,indent=2)
    print(json.dumps({'module_endpoints':out['module_endpoint_count'],'fresh_authors':out['formal_fresh_authors'],'corrections':out['corrections'],'blocked':out['blocked_prepared_without_inbox']}))
if __name__=='__main__':main()
