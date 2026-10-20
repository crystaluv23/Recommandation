"""Read only the sealed Controller frontier; no constructors, roles or stage calls."""
import hashlib,json,subprocess
from pathlib import Path
REPO=Path(__file__).resolve().parents[4]
OUT=Path(__file__).resolve().parent
OLD=REPO/'runs/diagnostics/reviewed_slow_feedback_stage_20261021_v1'
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
read=lambda p:json.loads(p.read_text())
files=[OLD/n for n in ('completion.json','manifest.json','factory-input.json','reflection-boundary.json','controlled-page.json','controlled-page-read.json','controller-boundary.json','workspace/run_contract.json','workspace/experiments/cycles/cycle-0001/slow_input.json','workspace/experiments/cycles/cycle-0001/slow_memory_delta.json')]
files=[p for p in files if p.is_file()]
paths=['src/stock_opportunity_agent/research/signal_evolution.py','src/stock_opportunity_agent/research/mining_controller.py','src/stock_opportunity_agent/research/mining_role_model.py','scripts/run_reviewed_slow_feedback_stage.py','spec/scripts/run_reviewed_slow_feedback_stage.md']
files += [REPO/p for p in paths]
before={str(p):sha(p) for p in files}
factory=read(OLD/'factory-input.json');manifest=read(OLD/'manifest.json');boundary=read(OLD/'controller-boundary.json');target=manifest['native_prepared']['target_need_ref']
views=[]
for p in sorted((OLD/'exchange/inbox').glob('*.json')):
    row=read(p)
    for m in row['messages']:
        if m['role']!='user':continue
        try:body=json.loads(m['content'])
        except (ValueError,TypeError):continue
        if 'need_disposition_contract' in body:
            views.append((p,body));before[str(p)]=sha(p)
first=next((p,v) for p,v in views if 'last_invalid_action' not in v)
assert len(views)==2 and len(factory['backlog_needs'])==265
assert target=='reflection-7d08d205fe330564' and target in boundary['pending_need_refs']
assert all(first[1][k]==factory[k] for k in ('slow_method_memory','meta_memory_disclosures','prior_modality_footprints','research_axis','label_map'))
report={
 'revision':subprocess.check_output(['git','rev-parse','HEAD'],cwd=REPO,text=True).strip(),
 'scope':'Design and persisted-source verification only. No native constructors, execution, role request, budget reuse, Signal, global source mutation, or old-stage reentry.',
 'actual_frontier':{'target_need_ref':target,'full_backlog':265,'pending_after_v1':len(boundary['pending_need_refs']),'target_still_pending':True,'native_first_controller_inbox':str(first[0]),'first_and_correction_views':len(views),'accepted_reflection_hash':read(OLD/'reflection-boundary.json')['slow_memory_hash'],'factory_fields_match_first_wire':['slow_method_memory','meta_memory_disclosures','prior_modality_footprints','research_axis','label_map'],'old_target_acceptance':'0/1 permanently retained'},
 'source_findings':[
  {'file':paths[0],'lines':'6465-6607','finding':'_run_controller_mining_axis calls _mining_context before making two seed Controllers. That context can request fresh original/method reads; calling the whole factory is not inherently Controller-only.'},
  {'file':paths[0],'lines':'6559-6563','finding':'save_need_unit is a nested closure, not EvolutionWorkspace API. It writes native schema mining-need-disposition-unit-v1 to experiments/cycles/cycle-ID/mining_need_units/hash(axis,seed)/result_hash.json with _write_or_verify_json.'},
  {'file':paths[1],'lines':'1728-1762','finding':'Original Controller validates issued base_hash, disclosed unresolved need refs, row semantics, retains invalid siblings, updates native pending state and calls progress sink only after accepted rows. No new task/answer schema is needed.'},
  {'file':paths[1],'lines':'1863-1897','finding':'Real ReflectionMemoryIndex affects even initial meta_info. Replacing it with None or a replay facade changes the input; factory-input alone is insufficient.'},
  {'file':paths[0],'lines':'8838-8859','finding':'Native memory-index construction uses PlanMetaMemory archive/profiles plus comparison sources/episodes under H1 scope. This is pure reconstructible work, distinct from later optional role reads.'}],
 'option_A':{'change':'New assigned-target profile in existing runner; freeze native target need_ref in task envelope with no route/disposition/rationale gold. New independent contract/root/limits; rerun full source selection, Reflect and Controller prefix.',
  'evidence':'Fresh end-to-end small composition under new assignment; original v1 remains 0/1, no transfer of successful prefix claims to new role outputs.',
  'risk':'Repeats already successful costly semantic prefix, introduces different selected originals/reflection and changes more than task assignment. More requests and more moving parts; not minimal discriminator.'},
 'option_B_recommended':{
  'boundary':'New assigned Controller-only experiment branching at sealed pre-first-Controller frontier. It imports accepted input artifacts as immutable provenance, not old execution authority and not a resume of v1. Old other-need unit is retained as provenance, not credited/applied a second time.',
  'minimal_product_refactor':['Extract current Controller constructor plus its original need-progress persistence closure into one private shared builder/sink used by _run_controller_mining_axis and the thin diagnostic. Preserve all arguments, original unit path recipe and _write_or_verify_json behavior. No general continuation framework/public schema.',
   'Factor the existing pure ReflectionMemoryIndex construction block only if necessary for exact rebuilding; both native context and diagnostic use the same source/scope algorithm. Never call _mining_context or _slow_method_view in this Controller-only boundary because their optional role reads would replay semantic prefix.'],
  'inputs':['All 265 backlog rows/order and native target identity from sealed manifest+factory.',
   'Exact accepted slow_input/sampling, slow_memory_delta, full 603908 provenance hash, six disclosure originals, briefs, and factory research_axis/label_map.',
   'Frozen approved case objects selected in original sampling order, existing qualified 1780 view, exact stable catalog/spec/skills, native identity guards and measurable evidence manifest.',
   'Real native memory index reconstructed from bound historical meta archive/profiles and accepted comparison sources/episodes; original schema/scope validation retained.',
   'Constructor parameters absent from factory JSON: case_pairs, measurable_evidence_manifest, catalog/originals, identity_aliases, attribute_vocabulary, memory_index, native heavy/light/browse limits. Freeze or reconstruct them from exact named sources; no defaults guessed to match outcome.'],
  'pre_dispatch_gate':'Construct actual Controller with the shared builder, execute the same controlled inspect_catalog/backlog initialization, compare complete canonical first model view with original first inbox (including catalog, memory, page hash, base_hash and budget). Any unavoidable change must be explicit contract delta before execution; never coerce it away. The only planned semantic delta is wrapper task assignment of native need_ref, no route/answer.',
  'new_authority':'Separate fixed destination/profile and fresh explicitly authorized limited Controller budget, not original run_contract or remaining old allowance. If a contract is used, bind identical copies at actual workspace and stage. No complete_cycle, original source/reflect calls, Engine-prefix-success claim, stable publication or duplicate learning event credit.',
  'allowed_actions':'Only native backlog inspect if required and record_need_dispositions for the assigned native need. Full backlog stays visible/order unchanged; stage envelope states assigned target and stops at first original accepted progress-unit write, even if semantically wrong. Wrong target/unsupported action/correction exhaustion retains failure and original answer.',
  'counts_and_acceptance':'New target denominator 1, old v1 0/1 retained. First answer, native correction, raw/cache/receipt, row validation, exact native saved unit and pending target reviewed separately. No answer/route oracle reaches role. Budget requires root freeze; initial+one existing native correction is sufficient proposed minimum, no automatic extension.',
  'proof_limit':'Demonstrates actual native target handoff and sink from an accepted prefix; does not establish a fresh full Engine/S1-S2 run, autonomous task search, all-backlog processing, Mining/new measurement or independent benefit.',
  'unverified':'No Controller-frontier native reconstruction or equality probe executed in this design task. If original memory-index lineage cannot be reproduced exactly without a role, stop and revise boundary before new model request.'},
 'safe_preflight_proposal':['Shared builder/sink versus original factory constructor arguments and exact saved unit equality; source hashes unchanged.',
   'Reconstructed initial native view exact original-wire equality, including real memory index and six original disclosures; no caller allowed during prepare.',
   'Assignment wrapper contains native need_ref but no route/gold; wrong/non-native/duplicate/removed target and source/code drift reject before first role.',
   'Typed invalid row uses existing one correction; no accepted row means no sink success; partial sibling rows/pending count remain native.',
   'Old completed stage unchanged, new fresh fixed root/contract/limits and no source/reflect/Signal/label/GET/other seed/candidate actions.'],
 'bindings':[{'path':p,'sha256':v} for p,v in before.items()]
}
assert report['revision']=='55fb1f5ee1ed0fdbac455b46451fc829af809b33'
assert all(sha(Path(p))==v for p,v in before.items())
output=OUT/'source-frontier-review.json'
with output.open('x') as f:json.dump(report,f,indent=2,sort_keys=True);f.write('\n')
print(json.dumps({'output':str(output),'sha256':sha(output),'bound_paths':len(before),'source_bytes_unchanged':True,'target':target}))
