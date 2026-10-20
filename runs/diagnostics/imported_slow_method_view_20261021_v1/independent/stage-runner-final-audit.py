"""Read retained zero-answer integration artifacts only; never stage commands."""
from pathlib import Path
import hashlib
import json
import tempfile
from scripts import run_reviewed_slow_feedback_stage as native

REPO=Path.cwd()
OWN=Path(__file__).resolve().parent
P=OWN.parent/'oracle/temp-native-preflight'
STAGE=P/'stage-artifacts'


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def read(path):
    return json.loads(Path(path).read_text())


def canonical(value):
    return hashlib.sha256(json.dumps(value,sort_keys=True,separators=(',',':')).encode()).hexdigest()


if __name__=='__main__':
    source=REPO/'scripts/run_reviewed_slow_feedback_stage.py'
    assert sha(source)=='a1acad66f4f83935bb5ccdb8834ec32ad064c42a1ab98ac84b76d2f6bb1209f9'
    result=read(P/'result.json');manifest=read(STAGE/'manifest.json')
    before=read(P/'sources-before.json');after=read(P/'sources-after.json')
    assert before==after and len(before['bindings'])==4408 and before['hash']==canonical(before['bindings'])
    assert result['production_connections_patched']==[] and result['only_patch']=='STAGE_ROOT'
    assert result['prepare']['status']=='prepared_not_dispatched' and result['advance']['status']=='pending'
    assert result['dispatches']==result['receipt_count']==result['answer_count']==result['submitted_answers']==0
    assert not native.STAGE_ROOT.exists()
    assert canonical({k:v for k,v in manifest.items() if k!='manifest_hash'})==manifest['manifest_hash']==result['prepare']['manifest_hash']
    contract=read(STAGE/'run_contract.json')
    assert (STAGE/'run_contract.json').read_bytes()==(STAGE/'workspace/run_contract.json').read_bytes()
    assert canonical(contract['contract'])==contract['contract_hash'] and contract['contract']==manifest['run_contract']
    assert contract['contract']['cycle_mode']=='slow_only' and contract['contract']['limits']['plan_rounds_per_signal_cycle']==0
    assert contract['contract']['slow_history_manifest_hash']==native.HISTORY_HASH
    missing=[]
    for relative,value in manifest['copied_files'].items():
        assert sha(native.SOURCE/'stage'/relative)==value
        target=STAGE/'workspace'/relative
        if target.exists():assert sha(target)==value
        else:missing.append(relative)
    state=read(STAGE/'workspace/state.json');cycle=read(STAGE/'workspace/cycle_state.json')
    assert state['last_completed_round']==cycle['last_completed_cycle']==0 and cycle['active_cycle']['phase']=='slow_loop'
    slow=read(STAGE/'workspace/experiments/cycles/cycle-0001/slow_input.json')
    assert canonical(slow)==manifest['native_prepared']['slow_input_hash']
    assert len(slow['feedback_rows'])==len(slow['source_manifest'])==4493
    refs=[row['feedback_ref'] for row in slow['feedback_rows']]
    assert len(set(refs))==4493 and canonical(refs)==manifest['native_prepared']['feedback_refs_hash']
    assert canonical(slow['source_manifest'])==manifest['native_prepared']['source_manifest_hash']
    assert manifest['native_prepared']['target_need_ref']==result['prepare']['target_need_ref']=='reflection-7d08d205fe330564'
    sample=slow['sampling_manifest'];dev=set(sample['dev_case_ids']);check=set(sample['check_case_ids'])
    assert dev and check and not dev&check and len(dev|check)<=16
    qpaths=list((STAGE/'transport/requests').glob('*.json'));ipaths=list((STAGE/'exchange/inbox').glob('*.json'))
    assert len(qpaths)==len(ipaths)==1
    request=read(qpaths[0]);inbox=read(ipaths[0]);key=request['request_hash']
    assert canonical(request['request'])==key==inbox['request_hash']==result['advance']['request_hash']
    assert request['request']['messages']==inbox['messages'] and request['request']['stage']=='slow_source_read'
    assert request['request']['max_output_tokens']==512 and sha(ipaths[0])==result['advance']['inbox_sha256']
    payload=json.loads(next(row['content'] for row in request['request']['messages'] if row['role']=='user'))
    assert payload['role_scope']=='reflection' and payload['source_read_contract_version']=='slow-source-read-v1'
    assert not (STAGE/'failure.json').exists() and not (STAGE/'completion.json').exists()
    budget=native._Budget(STAGE/'transport/requests')
    assert len(budget.requests)==1 and next(iter(budget.requests.values()))['reservation']<=131072
    controls=[]
    with tempfile.TemporaryDirectory() as tmp:
        root=Path(tmp);(root/'workspace').mkdir();body={'synthetic':True}
        envelope={'contract':body,'contract_hash':canonical(body)}
        (root/'run_contract.json').write_text(json.dumps(envelope))
        try:native._verify_contracts(root,body)
        except FileNotFoundError:controls.append('missing workspace copy rejects')
        else:raise AssertionError('missing copy accepted')
        (root/'workspace/run_contract.json').write_bytes((root/'run_contract.json').read_bytes())
        native._verify_contracts(root,body);controls.append('exact dual copy accepted')
        changed={'synthetic':False}
        (root/'workspace/run_contract.json').write_text(json.dumps({'contract':changed,'contract_hash':canonical(changed)}))
        try:native._verify_contracts(root,body)
        except native.StageRejected:controls.append('coherently changed workspace copy rejects')
        else:raise AssertionError('changed copy accepted')
    assert sha(source)=='a1acad66f4f83935bb5ccdb8834ec32ad064c42a1ab98ac84b76d2f6bb1209f9'
    report={'status':'PASS_bounded_preflight_through_first_zero_answer_native_inbox',
        'bindings':{str(p):sha(p) for p in (source,native.SPEC,REPO/'tests/test_reviewed_slow_feedback_stage.py',
            P/'run.py',P/'result.json',P/'sources-before.json',P/'sources-after.json',STAGE/'manifest.json',qpaths[0],ipaths[0])},
        'actual_temporary_connections':{'only_patch':'STAGE_ROOT','native_Engine_and_qualified_store':True,
            'full_feedback_denominator':4493,'target_need_ref':manifest['native_prepared']['target_need_ref'],
            'source_before_after_bindings':4408,'same_new_dual_contract':True,
            'request_hash':key,'first_native_stage':'slow_source_read',
            'reservation':next(iter(budget.requests.values()))['reservation'],
            'inbox_messages_exact':True,'answers':0,'receipts':0,'agent_dispatches':0,
            'completed_fast_round':0,'completed_slow_cycle':0,'formal_root_exists':False},
        'dual_contract_temp_controls':controls,
        'retained_copy_evidence':{'expected_copy_map':len(manifest['copied_files']),
            'all_expected_source_bytes_current_equal_map':True,'copied_files_not_retained_here':len(missing),
            'limitation':'Saved temporary artifacts omit historical copy directories. Original native prepare/advance _preserved checks and guard establish execution-time equality; reviewer cannot rehash the removed temporary destination copies. No rerun requested.'},
        'resolved_blocker':'Same new frozen contract is now stored and byte-verified under the actual workspace before native import/knowledge readers; no authority gate weakened.',
        'audit_correction':'The file named stage-runner-original-a1acad... was captured after the fix raced with review. It is the corrected candidate, not an exact old missing-contract source snapshot. Initial review retained but that old-byte attribution is withdrawn; initial read text and independent native importer counterexample support the old diagnosis, not an actual failed stage execution.',
        'harness_failure_retained':'The first read-only audit assumed all temp copied directories were preserved and stopped at a missing copied manifest. This is missing retained evidence, not a native prepare failure. No stage operation was rerun.',
        'static_scope':['Discovery-only dev/check ids; forty identities provide aliases, not general outcome disclosure. Existing nonempty direct-modality footprint channel rejects before dispatch.',
            'Unique request journal reservations reconstruct exact family/8request/131072perrequest/1048576total limits before receive; old experiment budgets not reused.',
            'Original Engine factory/full backlog and explicitly controlled native page retained. Controller system prompt adds a declared execution envelope; not byte-identical native prompt or autonomous retrieval.',
            'Original need sink returns before EvolutionControlFlow boundary exits ahead of a later call/seed; module remains partial_running, semantics unreviewed.',
            'Terminal restore only checks saved bytes without construction or further calls.'],
        'limits':['No prepare, advance, dispatch, Signal, API, GET, LabelStore, full Slow or real source mutation was executed by this review.',
            'Authorized temporary integration reached only one pending selector. Fresh reflection/Controller answers and need sink semantics remain future acceptance.',
            'Saved4408 before/after metadata compared exactly; underlying4408 sources were not independently rehashed again. Expected copied history source files and retained input/contracts/request/inbox were read directly.',
            'Actual mixed approved case file was not deserialized by this independent review, and no retrospective outcome values are copied to this report.']}
    (OWN/'stage-runner-final-review.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps({'status':report['status'],'sha256':sha(OWN/'stage-runner-final-review.json'),
        'retained_missing_copy_count':len(missing),'reservation':next(iter(budget.requests.values()))['reservation']}))
