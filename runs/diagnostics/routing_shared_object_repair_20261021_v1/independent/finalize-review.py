"""Read completed offline probes and preservation bindings; execute no product code."""
from pathlib import Path
from datetime import datetime,timezone
import ast,json,hashlib
R=Path('/Users/l/Project/Recommandation');D=R/'runs/diagnostics/routing_shared_object_repair_20261021_v1';O=D/'independent';S=R/'runs/diagnostics/gpre_native_routing_20261021_v1/stage'
def read(p):return json.loads(p.read_text())
def h(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def b(p):return {'path':str(p),'sha256':h(p),'bytes':p.stat().st_size}
source=R/'src/stock_opportunity_agent/research/evolution_research_validation.py';spec=R/'spec/src/stock_opportunity_agent/research/evolution_research_validation.md';tests=R/'tests/test_evolution_routing_plan_roles.py'
assert h(source)=='92cabdd835ebab45d5167dc25e5d9f5e8e3909a2b25219c18d52ca4de658e946'
assert h(spec)=='fe287bfc2572685dde82b474e5830602032bd072cde05512bb639be45fe9840a'
assert h(tests)=='57b25ae8236279ba92b2f1db4e210600dc59e49db9ef346a435c81f6bbf65431'
old=O/'original-9ac20df4-validation.py';assert h(old)=='8a8b0e797bb3e66bddeb66f828db07c8e20b35f881a0a8ea2b5fafdf49faf55f'
def outside_helper(p):return [ast.dump(n,include_attributes=False) for n in ast.parse(p.read_text()).body if not (isinstance(n,(ast.FunctionDef,ast.AsyncFunctionDef)) and n.name=='_shared_distinctive_phrase')]
assert outside_helper(old)==outside_helper(source)
base=read(O/'baseline-9ac-results.json');first=read(O/'candidate-results.json');final=read(O/'final-candidate-results.json');multi=read(O/'final-candidate-typed-head-results.json');sole=read(O/'final-sole-head-candidate-results.json');oldhead=read(O/'baseline-9ac-typed-head-results.json');oldsole=read(O/'rootexact-717-sole-head-baseline-9ac-results.json');initialsole=read(O/'candidate-717-sole-head-baseline-9ac-results.json')
assert base['passed']==8 and final['passed']==first['passed']==12 and final['case_count']==14
assert [r['case_id'] for r in final['results'] if not r['pass']]==['p05_same_facet_distinct_explicit_objects','p06_same_facet_disjoint_literal_time_windows']
assert all(r['pass'] for r in final['results'][:4]) and all(r['pass'] for r in final['results'][4:12])
assert all(r['native']['siblings_exact'] for r in final['results']) and final['extras'][0]['pass']
assert multi['extras'][0]['pass'] and sole['extras'][0]['pass'] and not oldhead['extras'][0]['pass'] and not oldsole['extras'][0]['pass']
for v in (base,first,final,multi,sole,oldhead,oldsole):assert v['forbidden_calls']==[]
assert oldsole['helper_module_file_binding']['sha256']=='71731eab6ccb0d4567eedbb964de714780d296e58a49a23089aeb4ae5905675a'
assert oldsole['helper_code_filename']==oldsole['helper_module_file']
assert base['helper_module_file_binding']['sha256']==h(old) and base['helper_code_filename']==str(old)
assert final['helper_module_file_binding']['sha256']==h(source) and final['helper_code_filename']==str(source)
assert base['active_parser']['sha256']==h(R/'src/stock_opportunity_agent/research/evolution_plan_roles.py')=='29f1b3c057dc825ca77bed377a3f3be329c9eb6914ad5ad24774f88281d8aa07'
assert h(R/'src/stock_opportunity_agent/research/evolution_output_validation.py')=='4a7f169d9a7362ff75a64873aa2c02760e1e9a036e639daa3eea5d79a10b2bc0'
assert 'residual_need must be grounded' in initialsole['extras'][0]['result']['feedback'][0]['validation_error']
assert 'residual_need must be grounded' not in oldsole['extras'][0]['result']['feedback'][0]['validation_error']
assert oldsole['extras'][0]['result']['selected'][1]['reason_code']=='answer_need'
assert sole['extras'][0]['result']['selected'][1]['reason_code']=='assess_applicability'
assert 'premium' in sole['extras'][0]['result']['feedback'][0]['validation_error']
actual_review=read(R/'runs/diagnostics/gpre_native_routing_20261021_v1/independent-preflight/actual-routing-review.json')
for row in actual_review['stage_files_current']:assert h(Path(row['path']))==row['sha256'],row['path']
man=read(S/'manifest.json');source_rows=man['source_files']
for row in source_rows:assert h(Path(row['path']))==row['sha256'],row['path']
code_drift=[]
for row in man['code_files']:
 if h(Path(row['path']))!=row['sha256']:code_drift.append({'original':row,'current':b(Path(row['path']))})
assert len(code_drift)==1 and code_drift[0]['current']['path']==str(source)
preserve=read(S.parent/'root/before-preservation.json')
for row in preserve['files']:assert h(R/row['path'])==row['sha256']
for name,expect in [('frozen-cases-v3.json','6de09ea83f854dd541a65e1927e832e3a3b14dbe75b423c3020a2cf65790a258'),('typed-head-attack-expectation.json','16bb49a10c36363c3b6d695458e41909e45be9b5042d1d64b90db7262dcb5661'),('sole-retained-head-expectation-root-exact.json','985ed32c8feb0bb7cc0c5ebc62a7d7d6d6f2f616af68d3f1e3699eeed4e9b662')]:assert h(O/name)==expect
files=['frozen-cases.json','frozen-cases-v2.json','frozen-cases-v3.json','typed-head-attack-expectation.json','sole-retained-head-expectation.json','sole-retained-head-expectation-v2.json','sole-retained-head-expectation-root-exact.json','probe.py','probe-before-sole-clock-fix.py','original-9ac20df4-validation.py','candidate-717-before-sole-head.py','baseline-9ac-results.json','baseline-9ac.log','baseline-9ac-typed-head-results.json','baseline-9ac-typed-head.log','candidate-results.json','candidate.log','candidate-typed-head-results.json','candidate-typed-head.log','candidate-717-sole-head-baseline-9ac-results.json','candidate-717-sole-head.log','candidate-717-clockaligned-sole-head-baseline-9ac-results.json','candidate-717-sole-clockaligned.log','rootexact-717-sole-head-baseline-9ac-results.json','rootexact-717-sole-head.log','final-candidate-results.json','final-candidate.log','final-candidate-typed-head-results.json','final-candidate-typed-head.log','final-sole-head-candidate-results.json','final-candidate-sole-head.log']
report={'status':'BOUNDED_CORE_REPAIR_VERIFIED_WITH_TWO_EXISTING_SCOPE_FALSE_REJECTIONS_OPEN','reviewed_at_utc':datetime.now(timezone.utc).isoformat(),
 'candidate':{'source':b(source),'spec':b(spec),'author_tests':b(tests),'AST_outside_shared_helper_identical_to_9ac':True,'unchanged_native_parser':b(R/'src/stock_opportunity_agent/research/evolution_plan_roles.py'),'unchanged_typed_repair_and_fallback':b(R/'src/stock_opportunity_agent/research/evolution_output_validation.py')},
 'fixed_counts':{'total_independent_helper_native_cases':14,'final_passed':12,'core_shared_object_positives':4,'core_shared_object_positives_passed':4,'negative_controls':8,'negative_controls_passed':8,'adjacent_scope_positives':2,'adjacent_scope_positives_passed':0,'correct_typed_reason_repair':1,'correct_typed_reason_repair_passed':1,'multi_retained_head_two_answer_attack_rejected':1,'sole_retained_head_two_answer_attack_rejected':1},
 'old_vs_candidate':{'old9ac_helper':b(old),'old9ac_actual_module_file':base['helper_module_file'],'old9ac_actual_code_filename':base['helper_code_filename'],'old9ac14_passed':8,'old9ac_correct_typed_repair_passed':0,'old9ac_multihead_secondanswer_wrongly_admitted':True,
  'intermediate717_14_passed':12,'intermediate717_multihead_rejected':True,'intermediate717_solehead_secondanswer_wrongly_admitted':True,'final92ca_multi_and_solehead_rejected':True,
  'oldisolation_limit':'Exactoldhelper module and filename/hash are independent; nativeplanroles/typedfallback are byte-identical to9ac and common tobothruns. This is not an isolatedfulloldcheckout or freshmodel.'},
 'confirmed':['ActualsealedUHP row and lowercase/multiword/semicolon/reorderedobject variants now retain directpartial ononeofflinefirstanswer without propernounlookup.','True retainedsalesvolume/premium/multi-facet claims, missingmodifier, cosmeticresidual, substringlookalikes, no-literal-split and postcutoffactuals do not retain directownership.','Singleliteralretainedhead now generates premium feedback rather than sharedobject; native typed secondanswer thatonlydeletesobject still fails completevalidation and usesexistingcontextfallback.','A legitimate typedreason-only correction is merged and completelyreparsed; originalfinance/liquiditysiblings remainunchanged.','All14cases and extra controls preservevalidsiblings; actualnativeSignalSelectionDecision.to_dict is JSON persisted/reread in independenttemp, without RawInfoStore or schema changes.'],
 'known_open':[
  {'case_id':'p05_same_facet_distinct_explicit_objects','verdict':'EXISTING_FALSE_REJECTION_PRESERVED','example':'OrionData commitments answered versus AuroraSensor commitments retained','reason':'Samefacet attached to differentexplicitobjects is semanticallyseparable, but current2-arm/overlappedfacet guard remainsconservative andflags bindingofftakecommitment. Old9ac alreadyfails; finaldoesnotcloseit.'},
  {'case_id':'p06_same_facet_disjoint_literal_time_windows','verdict':'EXISTING_NATIVE_FALSE_REJECTION_PRESERVED','example':'Sameproduct/commitment recent180day disclosedwindow answered versus prewindow still-effectivecommitments retained','reason':'The explicitnonoverlappingtime scopes are legitimatepartial, but actualnativeparser stillrejects sharedfacet. Standalonehelpernotforcedtoresolvealltemporalpolicy; fullparsercontrol demonstrates remaininggap. Old9ac alreadyfails.'}],
 'structural_limits':'Positiveexception is narrow target-derivednounlistproof:>=3arms, localcoordinatedarms requiremultiwordanchors, orderedfirstobjectprefix, independentlywitnessedanswered andstrongretainedfirstarm. A weakhead alone cannot justifypositiveexemption but can proveconflict. It is not a generalsemantic/object/time parser; ambiguityretains oldconservativeguard. No propernounlist, globaltopicignore, PIT weakening or typedpermission expansion.',
 'harness_and_case_refinements_preserved':[
  'Precandidate n05 changed threeansweredanchorwordlookalikes together; originalsingle commitmentship variant stillcontained bindingofftake literalanchors, so was ambiguous. Originalv1/v2files kept, core14 frozenbeforecandidate.',
  'Initialsolehead nativefixture used symbolic predictiontime target but explicitMay30 residual, causing an unrelatedresidualgrounding issue. Its nativefallback is NOT evidenceofsuccessfulsoleheadguard andis excluded frompositiveproof.',
  'Clockaligned independentsolefixture then rootexactauthorizedtarget/reason/residual produced onlyownership issue and actual717secondanswer misaccept. Finalsameexactrootfixture rejects. All initial/supplementaryfiles andhashes remain.'
 ],
 'preservation':{'original_completed_routing_stage_files_current_equal':len(actual_review['stage_files_current']),'original_case_authority_source_bindings_current_equal':len(source_rows),'root_original_preservation_files_current_equal':len(preserve['files']),'prior14_expectations_unchanged':True,'old_code_frozenfiles_not_rewritten':True,'intentional_current_code_revision_vs_oldstage':code_drift,
  'Registry_scope':'Independentcheck covers all1844frozen-sourcebindings, including actualfrozendefinitions. Author replay independentlyreports198Registryfilesbyteequal, citedasdriverartifact rather than claiming unavailableindependentbeforeinventory for every198file. OldruntimeRegistrytree notGittracked.'},
 'author_replay_corrob_only':b(D/'driver/original-portfolio-replay-v2.json'),
 'effects':{'freshroles':0,'API':0,'network':0,'LabelStore':0,'Signalcalculations':0,'RawInfoStore':0,'Registryfreeze_or_install':0,'completedstage_reentry':0,'product_edits_by_reviewer':0},
 'historical_verdict':'CompletedGPRE firstportfolio strict0/1 and actualfallback/entrybudgettrace unchanged. Offline1callreplay undernewhelper is not newfreshroutingpass, cannotoverwriteoldgold or claimF5/F7/MVP/benefit closed.',
 'bindings':[b(O/n) for n in files]}
p=O/'final-review.json';assert not p.exists();p.write_text(json.dumps(report,ensure_ascii=False,sort_keys=True,indent=2)+'\n');print(json.dumps({'status':report['status'],'review':b(p),'source':h(source),'independent_case_count':14,'passed':12,'open':['p05','p06'],'old_stage_preserved':len(actual_review['stage_files_current']),'old_source_preserved':len(source_rows)},indent=2))
