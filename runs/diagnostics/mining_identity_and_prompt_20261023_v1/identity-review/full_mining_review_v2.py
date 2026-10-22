"""Independent full Mining input-only projection/reservation review; no authors."""
import hashlib,json,re
from pathlib import Path
from unittest.mock import patch
import run_mining_locator_generalization_stage as driver
from stock_opportunity_agent.artifacts import canonical_json_hash
from stock_opportunity_agent.research.evolution_transport import _CaseIdentityProjection
from stock_opportunity_agent.research.evolution_core import _assert_identity_values_masked
R=Path(__file__).resolve().parent
REPO=R.parents[3]
B=REPO/'runs/diagnostics/mining_locator_generalization_20261023_v1'
PF=B/'preflight-v2'
def read(p):return json.loads(p.read_text())
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def bound(p):return {'path':str(p),'sha256':sha(p)}
def verify(row):
    p=Path(row['path']);assert sha(p)==row['sha256'],str(p)
    return row

def main():
    result=read(PF/'result.json')
    code_before=[verify(x) for x in result['code_files']]
    sources_before=[verify(x) for x in result['source_files']]
    tests_path=REPO/'runs/diagnostics/mining_identity_and_prompt_20261023_v1/associated-test-bindings.json'
    associated=read(tests_path)
    for row in associated['tested_files']:verify(row)
    assert associated['success'] and associated['tests_run']==341 and associated['network_calls']==0
    reference=read(B/'reference/source-reference.json')
    oldreview=read(B/'independent/final-query-and-budget-review.json')
    for row in oldreview['budget_review']['requests']:verify(row['request'])
    oldfailure=B/'preflight/budget-failure.json'
    verify(oldreview['budget_review']['record'])
    stage_checks=[]
    for row in oldreview['old_stage_preservation']['terminals']:
        verify(row['terminal']);stage_checks.append(row['terminal'])
    driver.configure()
    native=driver.module
    check_root=R/'full-mining-rebuild-v2'
    check_root.mkdir(exist_ok=False)
    inputs,_=driver.authorities()
    samples=[]
    with native.guards():
        for key in ('a','b'):
            sample=inputs[key]
            original_ref=next(x for x in reference['samples'] if x['case_ref']==sample['case_ref'])
            assert sample['case_id']==original_ref['case_id'] and sample['cutoff']==original_ref['prediction_cutoff']
            assert sample['expected_source']==original_ref['source_file']
            verify(original_ref['source_file'])
            root=check_root/key;root.mkdir()
            client=native.make_client(root,sample,{'limits':native.LIMITS},input_only=True)
            controller=driver.build_controller(root,sample,client)
            projection=_CaseIdentityProjection((sample['case_id'],sample['company_id']),'','',expand_aliases=False)
            aliases=(sample['case_id'],sample['company_id'])
            request_checks=[]; reservations=[]
            for step in range(1,5):
                view=controller._model_view()
                before=set((root/'requests').glob('*.json'))
                try:controller.model.next_action(view)
                except native.InputCaptured:pass
                else:raise AssertionError('input-only rebuild crossed model boundary')
                new=set((root/'requests').glob('*.json'))-before
                assert len(new)==1
                rebuilt=new.pop(); rebuilt_record=read(rebuilt)
                selector=read(PF/key/f'selector-{step:03d}.json')
                original_path=Path(selector['request']['path']);verify(selector['request'])
                original=read(original_path)
                assert original==rebuilt_record,'fresh native composition differs'
                req=original['request'];assert canonical_json_hash(req)==original['request_hash']==original_path.stem
                assert req['max_output_tokens']==2000
                actual_messages=req['messages']
                visible=json.loads(next(x['content'] for x in actual_messages if x['role']=='user'))
                system=next(x['content'] for x in actual_messages if x['role']=='system')
                preamble='Return exactly one JSON object and no non-JSON text. '
                assert system.startswith(preamble)
                canonical_system=system[len(preamble):]
                assert '[ANON_ID_' not in canonical_system
                projected,inverse=projection.project({'system_prompt':canonical_system,'payload':view})
                assert projected['payload']==visible
                assert preamble+projected['system_prompt']==system
                assert projection.restore(visible,inverse)==view
                assert read(PF/key/f'view-{step:03d}.json')==view
                reservation=len(json.dumps(actual_messages,ensure_ascii=False,sort_keys=True,separators=(',',':')).encode())+2000
                estimate=client.estimate_json_request_tokens(system_prompt=canonical_system,payload=view,allow_outcomes=True,anonymous_aliases=aliases,max_output_tokens=2000,temperature=.2)
                assert estimate==reservation<=32768
                reservations.append(reservation)
                _assert_identity_values_masked(actual_messages,aliases)
                wire=json.dumps(actual_messages,ensure_ascii=False)
                assert not re.search(r'(?<![A-Za-z0-9])\d{10}-\d{2}-\d{6}(?![A-Za-z0-9])',wire)
                assert not re.search(r'/Archives/edgar/data/\d+',wire,re.I)
                assert original_ref['document_outer_except_content']['metadata']['accession_number'] not in wire
                for row in view.get('structured_read_progress',{}).get('items',[]):
                    assert row['fact']['value'] in row['masked']
                    assert row['content_hash']==original_ref['document_outer_except_content']['content_hash']
                expected_action={'action':'compare_groups','concepts':[sample['concept']]} if step==1 else {'action':'read_span','fact_ref':driver.visible_operand(visible,sample['concept'],'latest'if step==2 else'comparable_prior')}if step<4 else {'action':'record_deferred'}
                assert {k:v for k,v in selector['action'].items()if k!='rationale'}==expected_action
                if step>1:
                    assert visible['comparison_progress']['snapshot_status']=='current'
                request_checks.append({'step':step,'request':bound(original_path),'native_rebuild_identical':True,'estimate_equals_reservation':True,'reservation':reservation,'identity_aliases_and_source_coordinate_residuals':0,'inverse_restores_entire_canonical_view':True,'read_receipts':len(visible['structured_read_progress']['items']),'next_ref_selected_from_current_wire':True})
                if step<4:
                    action=selector['action'];controller._validate_action_shape(action);controller._execute(action['action'],action)
            assert reservations==result['reservations'][key]
            assert sum(reservations)<=98304
            final=controller._model_view()
            receipts=final['structured_read_progress']['items']
            assert len(receipts)==2 and final['structured_read_progress']['selection_is_exhaustive']
            assert len({r['fact_ref']for r in receipts})==2
            assert all(r['case_refs']==[sample['case_ref']] and r['fact']['concept']==sample['concept']for r in receipts)
            # Whole source receipts/typed facts derive from the same persisted source document and exact source hashes.
            for r in receipts:
                fact=controller._facts[r['fact_ref']]
                assert str(fact.value)==r['fact']['value'] and fact.unit==r['fact']['unit']
                assert fact.taxonomy==r['fact']['taxonomy']
                assert r['document_ref'].startswith('document-'+original_ref['document_outer_except_content']['document_id'])
            assert not list(root.rglob('inbox/*.json')) and not list(root.rglob('outbox/*.txt'))
            samples.append({'sample':key,'case_ref':sample['case_ref'],'exact_source':original_ref['source_file'],'reservations':reservations,'aggregate_reservation':sum(reservations),'remaining':98304-sum(reservations),'requests':request_checks,'whole_successful_receipts':2,'source_qualification':'historical normalized selected-document scope; not complete/latest source or primary filing truth'})
    assert not list(PF.rglob('inbox/*.json')) and not list(PF.rglob('outbox/*.txt'))
    for row in code_before+sources_before:verify(row)
    for row in oldreview['budget_review']['requests']:verify(row['request'])
    verify(oldreview['budget_review']['record'])
    assert read(PF/'result.json')==result
    output={'schema_version':'independent-full-mining-preflight-v2-identity-review-v1','verdict':'Input-only preparation supported for both fixed source controls within original budget; no production author/fresh semantic acceptance yet.','preflight_result':bound(PF/'result.json'),'code_bindings_verified':len(code_before),'source_bindings_verified':len(sources_before),'associated_tests':{'record':bound(tests_path),'files_verified':len(associated['tested_files']),'tests':341,'network_calls':0,'independent_rerun':'not repeated; exact bound files and log record verified'},'samples':samples,'original_preflight_preserved':{'record':bound(oldfailure),'reservation':102563,'ceiling':98304,'old_prepared_requests':4,'old_prepared_hashes_unchanged':True,'old0671_namespace_terminal_records_unchanged':stage_checks},'zero_counts':{'production_inboxes':0,'production_answers':0,'external_api_get':0,'new_labels':0,'formal_stages_run':0,'completed_stage_reentry':0},'actual_chain':'Fresh Controller -> native RoleModel -> same StructuredRoleClient input-only serialization matches every saved actual request byte-for-byte; estimate=reservation; project/inverse restores every canonical view including document refs; each action/ref selected from its current wire only; two whole receipts persist in each final request.','limitations':['Preparation version has no consumed formalcase budget and does not resume old budget-limited0671 stage.','No model answer or semantic compliance result; frozen O1-O6 and full denominator2 remain unchanged.','Original synthetic19-case freeze was after initial candidate source existed; real8-request replay verifies exact original1951089/1746129 issuers independently.','This checks scoped known aliases and explicit SEC coordinates, not a proof of global anonymity or source economic truth.']}
    out=R/'full-mining-preflight-v2-review.json'
    with out.open('x')as f:json.dump(output,f,ensure_ascii=False,indent=2)
    acceptance={'schema_version':'independent-mining-preflight-v2-acceptance-v1','preflight_result':bound(PF/'result.json'),'independent_review':bound(out),'local_identity_review':bound(R/'local-final-review.json'),'source_reference':bound(B/'reference/source-reference.json'),'original_obligations':bound(B/'reference/prefreeze-obligations.json'),'obligation_supplement':bound(B/'reference/prefreeze-obligations-supplement.json'),'fixed_denominator':['source_1179','source_0770'],'scope':'Only input-onlypreparation/egress/reference-readiness is supported; retain independent O1-O6 verbatim, original98304aggregate/32768single/output2000/6decisions/6heavy. Fresh autonomous author actions, semantic source comparison and endpoint acceptance remain to be tested.','reservations':{s['sample']:s['aggregate_reservation']for s in samples},'preparation_only':True,'formal_semantic_controls_executed':0,'production_authors':0,'external_api_get':0,'old_preflight_failure_unchanged':True,'old0671_terminal_budget_unchanged':True,'review_does_not_authorize_full_successor_or_budget_reset':True}
    with(B/'reference/preflight-v2-acceptance.json').open('x')as f:json.dump(acceptance,f,ensure_ascii=False,indent=2)
    print(json.dumps({'review':str(out),'acceptance':str(B/'reference/preflight-v2-acceptance.json'),'aggregates':acceptance['reservations'],'source_bindings':len(sources_before),'code_bindings':len(code_before)}))
if __name__=='__main__':main()
