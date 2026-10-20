"""Read formal frozen manifest and first exact inbox only; no stage operations."""
from pathlib import Path
import hashlib
import json

REPO=Path.cwd()
ROOT=REPO/'runs/diagnostics/reviewed_slow_feedback_stage_20261021_v1'
OWN=Path(__file__).resolve().parent
KEY='c1d217e2d47453d3a37eea926e4bfe92000ba10d66a46886bd19e8dd82133ebb'


def sha(path):
    h=hashlib.sha256()
    with Path(path).open('rb') as stream:
        for value in iter(lambda:stream.read(1048576),b''):h.update(value)
    return h.hexdigest()


def read(path):
    return json.loads(Path(path).read_text())


def canonical(value):
    return hashlib.sha256(json.dumps(value,sort_keys=True,separators=(',',':')).encode()).hexdigest()


if __name__=='__main__':
    manifest=read(ROOT/'manifest.json')
    assert manifest['manifest_hash']=='3a4a0e30bfc60ee7bd383f3dee6e2bf446faed89d61a00ee3d8625e71b1705d1'
    assert canonical({k:v for k,v in manifest.items() if k!='manifest_hash'})==manifest['manifest_hash']
    for row in manifest['code']+manifest['source_bindings']:assert sha(row['path'])==row['sha256']
    assert len(manifest['code'])==175 and len(manifest['source_bindings'])==4
    for relative,h in manifest['copied_files'].items():assert sha(ROOT/'workspace'/relative)==h
    copied_actual={str(p.relative_to(ROOT/'workspace')):sha(p)
        for name in ('signals','slow_history','signals_candidates')
        for p in (ROOT/'workspace'/name).rglob('*') if p.is_file()}
    assert copied_actual==manifest['copied_files'] and len(copied_actual)==223
    contract=read(ROOT/'run_contract.json')
    assert (ROOT/'run_contract.json').read_bytes()==(ROOT/'workspace/run_contract.json').read_bytes()
    assert canonical(contract['contract'])==contract['contract_hash']
    assert contract['contract']==manifest['run_contract']
    assert sha(ROOT/'approved_cases.json')=='3c6a74fea9c3e29742d9759f11a9087cbb16726e17d509ec1f4dd7d5e2b48d3c'
    cap=manifest['stage_contract']
    assert cap['root']==str(ROOT.resolve()) and cap['max_calls']==8
    assert cap['per_request_logical_cap']==131072 and cap['total_logical_cap']==1048576
    assert cap['reflection']['corrections']==cap['controller']['corrections']==1
    assert cap['source_selectors']['max']==3 and cap['controller']['regular']==2
    assert contract['contract']['cycle_mode']=='slow_only' and contract['contract']['limits']['plan_rounds_per_signal_cycle']==0
    state=read(ROOT/'workspace/state.json');cycle=read(ROOT/'workspace/cycle_state.json')
    assert state['last_completed_round']==cycle['last_completed_cycle']==0
    assert cycle['active_cycle']['phase']=='slow_loop'
    slow=read(ROOT/'workspace/experiments/cycles/cycle-0001/slow_input.json')
    prepared=manifest['native_prepared'];refs=[row['feedback_ref'] for row in slow['feedback_rows']]
    assert len(refs)==len(set(refs))==len(slow['source_manifest'])==prepared['full_feedback_count']==4493
    assert canonical(refs)==prepared['feedback_refs_hash']=='6112482ca7fd11dea4158eda5a78eaeec1ea365fa4d715fecb02b127ed16124e'
    assert canonical(slow['source_manifest'])==prepared['source_manifest_hash']=='5b2864643344158f303a2a3f2121fd633688a5eb32fdd7fdbb12a557ce753a21'
    assert canonical(slow)==prepared['slow_input_hash']
    assert prepared['target_need_ref']=='reflection-7d08d205fe330564'
    temp=read(OWN.parent/'oracle/temp-native-preflight/stage-artifacts/manifest.json')
    assert prepared['feedback_refs_hash']==temp['native_prepared']['feedback_refs_hash']
    assert prepared['source_manifest_hash']==temp['native_prepared']['source_manifest_hash']
    assert prepared['target_action_hash']==temp['native_prepared']['target_action_hash']
    qpath=ROOT/'transport/requests'/f'{KEY}.json';ipath=ROOT/'exchange/inbox'/f'{KEY}.json'
    request=read(qpath);inbox=read(ipath)
    assert canonical(request['request'])==request['request_hash']==inbox['request_hash']==KEY
    assert request['request']['contract_hash']==contract['contract_hash']
    assert request['request']['messages']==inbox['messages']
    assert request['request']['stage']=='slow_source_read' and request['request']['max_output_tokens']==512
    assert sha(ipath)=='02357be8dee9fc4fd6d7b0b0cefd801b46c248f399e26754b5f41044193a5996'
    reservation=len(json.dumps(request['request']['messages'],ensure_ascii=False,sort_keys=True,separators=(',',':')).encode())+512
    assert reservation<=131072 and reservation<=1048576
    payload=json.loads(next(row['content'] for row in request['request']['messages'] if row['role']=='user'))
    assert payload['role_scope']=='reflection' and payload['source_read_contract_version']=='slow-source-read-v1'
    assert set(payload)=={'available_count','available_sources','current_view','deferred_count','included_count',
        'omitted_available_sources','role_scope','source_read_contract_version','validation_feedback'}
    assert all(not row['has_modality_metrics'] for row in manifest['check_footprint_preflight'])
    report={'status':'PASS_formal_frozen_initial_request_only',
        'manifest_hash':manifest['manifest_hash'],'code_bindings_verified':175,'direct_source_bindings_verified':4,
        'copied_population_bytes_verified':223,'dual_contract_exact':True,
        'full_feedback_count':4493,'feedback_refs_hash':prepared['feedback_refs_hash'],
        'permission_catalog_hash':prepared['source_manifest_hash'],'target_need_ref':prepared['target_need_ref'],
        'same_fixed_feedback_scope_and_action_as_zero_answer_temp':True,
        'initial_request_hash':KEY,'initial_stage':'slow_source_read','initial_logical_reservation':reservation,
        'request_journal_hash_and_inbox_messages_exact':True,
        'budget':{'requests':8,'per_request':131072,'total':1048576,'selector':3,
            'reflection_first':1,'reflection_correction':1,'controller_regular':2,'controller_correction':1},
        'completed_pointers':[0,0],'source_check_footprint_preflight_clear':True,
        'native_payload_shape':'source selector catalog/read directory, not a disposition answer or private oracle',
        'bindings':{str(p):sha(p) for p in (ROOT/'manifest.json',ROOT/'run_contract.json',
            ROOT/'workspace/run_contract.json',qpath,ipath,Path(__file__))},
        'limits':['Only the first frozen request was read; no role79 or other unfinished/future output read.',
            'No prepare, advance, dispatch, model/API, GET, Store, Signal or LabelStore invoked.',
            'Actual approved mixed case file was stream-hashed, not deserialized. No retrospective outcome values copied to this audit.',
            'Manifest/hash integrity is not semantic correctness or model obedience. Later fresh reflection/controller/sink need separate actual review.',
            'This first source-selector request does not yet establish the declared Controller prompt authorization envelope was actually transmitted.']}
    out=OWN/'formal-initial-review.json';out.write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps({'status':report['status'],'review_sha256':sha(out),'reservation':reservation}))
