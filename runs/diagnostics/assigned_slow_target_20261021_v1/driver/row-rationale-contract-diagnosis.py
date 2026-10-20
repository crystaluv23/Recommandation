"""Inspect only the two sealed first Controller answers and current contracts.

Never opens the active correction's outbox; performs no Controller/model call.
"""
import hashlib,json,subprocess
from pathlib import Path
REPO=Path(__file__).resolve().parents[4]
OUT=Path(__file__).resolve().parent
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
read=lambda p:json.loads(p.read_text())
cases=[('v1_unassigned',REPO/'runs/diagnostics/reviewed_slow_feedback_stage_20261021_v1',
        '41b684543a85c2accdcbfccc64df1a80983d7b3ea7f57c147808a14d57e2c1af'),
       ('child_assigned',REPO/'runs/diagnostics/assigned_slow_target_20261021_v1/stage',
        '515b1e5b48b0c1ffbe036da03e93a3a0d6e96c4664fc6bb0fb538ee99b0a674e')]
paths=[];rows=[]
for name,root,key in cases:
    inbox=root/'exchange/inbox'/f'{key}.json';receipt=root/'exchange/receipts'/f'{key}.json';raw=root/'exchange/outbox'/f'{key}.txt'
    paths.extend([inbox,receipt,raw]);env=read(inbox);rec=read(receipt);answer=read(raw)
    assert rec['inbox_sha256']==sha(inbox) and rec['raw_output_sha256']==sha(raw)
    system=next(m['content'] for m in env['messages'] if m['role']=='system')
    payload=json.loads(next(m['content'] for m in env['messages'] if m['role']=='user'))
    excerpts=[];cursor=0
    while True:
        index=system.find('rationale',cursor)
        if index<0:break
        excerpts.append(system[max(0,index-90):min(len(system),index+180)])
        cursor=index+len('rationale')
    rows.append({'case':name,'request_hash':key,'agent_id':rec['agent_id'],
        'first_raw_sha256':sha(raw),'top_level_rationale_type':type(answer['rationale']).__name__,
        'need_disposition_row_types':[{'need_refs':type(r['need_refs']).__name__,
            'disposition':type(r['disposition']).__name__,'signal_refs':type(r['signal_refs']).__name__,
            'rationale':type(r['rationale']).__name__} for r in answer['need_dispositions']],
        'actual_initial_row_contract':payload['need_disposition_contract'],
        'system_rationale_excerpts':excerpts,'transport_output_contract':env['output_contract']})
assert all(r['top_level_rationale_type']=='list' and r['need_disposition_row_types'][0]['rationale']=='str' for r in rows)
sourcepaths=[REPO/p for p in ['src/stock_opportunity_agent/research/mining_role_model.py','src/stock_opportunity_agent/research/mining_controller.py','src/stock_opportunity_agent/research/repair.py','spec/src/stock_opportunity_agent/research/signal_mining_agent.md','scripts/run_assigned_slow_target_stage.py','spec/scripts/run_assigned_slow_target_stage.md']]
paths+=sourcepaths
before={str(p):sha(p) for p in paths}
report={
 'revision':subprocess.check_output(['git','rev-parse','HEAD'],cwd=REPO,text=True).strip(),
 'scope':'Read-only current frozen inputs/source. Only first v1 and first85 raw read; no86 raw read, role message, runtime construction, model, query, source modification or old-stage reentry.',
 'observations':rows,
 'contract_chain':[
  {'path':'src/stock_opportunity_agent/research/mining_role_model.py','lines':'32-33,113-125,237-239','finding':'Initial prompt explicitly requires assembled-action/top-level rationale non-empty array, then lists each need row fields but does not independently declare nested rationale type.'},
  {'path':'src/stock_opportunity_agent/research/mining_controller.py','lines':'553-560','finding':'Initial need_disposition_contract exposes state/ref/count/disposition permissions, no row field types or item schema.'},
  {'path':'src/stock_opportunity_agent/research/mining_controller.py','lines':'1572-1619','finding':'Runtime requires exact row keys and rationale non-empty list of nonblank strings. Scalar is rejected before accepted row, so progress remains absent for that row.'},
  {'path':'src/stock_opportunity_agent/research/mining_controller.py','lines':'1738-1758','finding':'Independent row errors are returned in no-progress InvalidMiningAction; this uses the normal full-action continuation, not a row-specific output_patch_contract. Successful valid siblings still persist.'},
  {'path':'src/stock_opportunity_agent/research/repair.py','lines':'641-654','finding':'Only top-level action rationale scalar wrapping is mechanical. No row-specific wrapping applies; automatically extending it would change repair authority and is not required for the proposed disclosure fix.'},
  {'path':'spec/src/stock_opportunity_agent/research/signal_mining_agent.md','lines':'34-54,418-424','finding':'Owning spec states rationale-array action grammar and existing row validator/independent progress; explicit nested author-facing schema is not sent in initial Controller view.'}],
 'judgment':{'observed':'Both independent first answers honored top-level array and used a scalar only in nested rationale. Native rejection is contract-consistent.',
    'attribution':'Authoring contract has a concrete missing nested-type disclosure. The general action instruction could suggest arrays, but it is not an explicit per-row declaration. Therefore do not classify these outputs solely as ignoring an unambiguous row-specific instruction.',
    'causal_limit':'No controlled fresh prompt variant has been executed. Two matching errors support the producer/validator seam; they do not prove why either role chose a scalar.',
    'not_changed':'Current85/86 execution and old target outcome remain under their existing contracts; no prompt patch or retry is authorized by this diagnosis.'},
 'minimal_proposal':{
    'owner_spec':'spec/src/stock_opportunity_agent/research/signal_mining_agent.md, incremental action shape and record_need_dispositions clauses',
    'shared_producer':'State explicitly in shared _MINING_CONTROLLER_PROMPT: top-level action.rationale AND every need_dispositions[i].rationale must be non-empty arrays of nonblank strings; one sentence is still a one-element array. Name need_refs/ signal_refs as arrays and disposition as enum string. No example disposition/answer for a case.',
    'bounded_view_option':'Use one private row-field description shared with initial need_disposition_contract (required exact keys/types/item constraints); system references this row contract. Reuse existing schema semantics, no new canonical field, validator framework or route gate. If two sentences in shared prompt suffice, avoid a new helper solely for bookkeeping.',
    'unchanged':['Current strict row validator, native one-correction budget','Independent sibling acceptance and pending state','Need ownership/ref/base_hash/source/PIT/budget guards','No automatic author text/route, no forced scalar conversion or stage-only patch','Terminal actions carrying need_dispositions follow the same row contract'],
    'test_scope':['Actual MiningAgentRoleModel outgoing initial payload/system contains explicit nested rationale shape; not just static source text.',
        'Native record_need_dispositions valid list[str] row writes original unit; scalar/empty/list empty-string/number/nested-array rows reject without silently accepting.',
        'Top-level list + nested scalar counterexample remains rejected; mixed valid+invalid siblings preserve valid progress and pending remainder.',
        'Existing top-level mechanical scalar wrapping remains unchanged; do not expand repair behavior implicitly.',
        'Ordinary initial and native correction/terminal paths preserve exact ref/base permissions and original one-correction ceiling.'],
    'future_fresh_evidence':'Only a separately authorized frozen stage can establish first-answer adherence after shared disclosure repair. Current stage is completed/pending under old frozen contract; never rerun its correct prefix to seek green.'},
 'bindings':[{'path':p,'sha256':value} for p,value in before.items()]
}
assert all(sha(Path(p))==value for p,value in before.items())
p=OUT/'row-rationale-contract-diagnosis.json';p.open('x').write(json.dumps(report,indent=2,sort_keys=True)+'\n')
print(json.dumps({'path':str(p),'sha256':sha(p),'read_first_answers':len(rows),'frozen_read_files_unchanged':True}))
