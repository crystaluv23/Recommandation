"""Read-only publication counterreview; fixture paths stop before any Signal execution."""
from dataclasses import asdict
import ast,copy,hashlib,json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
from stock_opportunity_agent import signal_library as lib
from stock_opportunity_agent.research.signal_evolution import SignalCandidateValidator,SignalEvolutionEngine
from stock_opportunity_agent.data.sec_company_facts import validate_company_fact_document_issuer
from stock_opportunity_agent.data.raw_info import RawInfoDocument
from datetime import datetime

ROOT=Path(__file__).resolve().parents[4];BASE=Path(__file__).resolve().parents[1];OUT=Path(__file__).resolve().parent
bindings={}
def read(path):
 p=Path(path);raw=p.read_bytes();bindings[str(p.resolve())]=hashlib.sha256(raw).hexdigest();return json.loads(raw)
def bind(path):
 p=Path(path);raw=p.read_bytes();bindings[str(p.resolve())]=hashlib.sha256(raw).hexdigest();return raw.decode()
def write(name,obj):
 p=OUT/name;assert not p.exists(),p;p.write_text(json.dumps(obj,indent=2,ensure_ascii=False)+'\n')
plan=read(ROOT/'runs/diagnostics/current_financial_apply_20261021_v1/native/stage/plan.json');authority=plan['group'];source_root=Path(authority['root'])
newdefs=read(ROOT/'runs/diagnostics/financial_period_policy_20261023_v1/independent/new-version-specs.json');fixtures=read(ROOT/'runs/diagnostics/financial_period_policy_20261023_v1/independent/lineage-fixtures.json')
driver_source=bind(BASE/'run_publication.py');ownspec=bind(ROOT/'spec/scripts/publish_approved_financial_versions.md');library_source=bind(ROOT/'src/stock_opportunity_agent/signal_library.py');bind(ROOT/'src/stock_opportunity_agent/research/signal_evolution.py');bind(ROOT/'spec/src/stock_opportunity_agent/signal_library.md')
log=bind('/tmp/approved-financial-publication-prepare.log')
legacy=[];cards=[]
for ref in authority['refs']:
 signal,v=ref.rsplit(':v',1);specpath=next(source_root.glob('*/'+signal+'/versions/v'+v+'/spec.json'));obj=read(specpath);spec=lib.SignalSpec.from_dict(obj);testdata=read(specpath.with_name('tests.json'))
 # Public metadata shape only: no original Registry constructor, freeze, fixture execution or publication.
 card=lib.SignalCard(signal_id=spec.signal_id,version=spec.version,category=spec.category,description=spec.description,execution_type=spec.execution_type,learned_profile={},research_status={},measurement_scope=lib.signal_measurement_scope(spec,deterministic_functions=lib.default_deterministic_signal_functions()))
 shaped=card.to_dict();json.loads(json.dumps(shaped));cards.append(shaped)
 if obj['category']=='financial' and obj['execution']['type']=='deterministic':
  missing=[]
  for i,fixture in enumerate(testdata['tests']):
   for j,raw in enumerate(fixture.get('documents',[])):
    body=json.loads(raw['content'])
    if body.get('schema_version')!='sec-company-facts-document-v1':continue
    # Reproduce only the issuer check, not a numeric Signal.
    clock=datetime.fromisoformat(raw.get('published_at',raw.get('available_at',fixture['as_of'])))
    d=RawInfoDocument.create(document_id=raw.get('document_id',f'identity_control_{i}_{j}'),company_id='capability_fixture',source_type=raw['source_type'],published_at=clock,available_at=datetime.fromisoformat(raw.get('available_at',clock.isoformat())),content=raw['content'],metadata=raw.get('metadata',{}))
    try:validate_company_fact_document_issuer(d,body)
    except Exception as exc:reason=f'{type(exc).__name__}: {exc}'
    else:reason=None
    missing.append(dict(fixture_index=i,document_index=j,fixture_company_id=fixture.get('company_id'),body_cik=body.get('cik'),metadata_cik=raw.get('metadata',{}).get('cik'),issuer_check=reason))
  assert missing and all(r['body_cik'] is None and r['metadata_cik'] is None and r['issuer_check'] for r in missing)
  legacy.append(dict(ref=ref,spec_path=str(specpath),tests_path=str(specpath.with_name('tests.json')),fixtures=len(testdata['tests']),source_identity_checks=missing))
assert len(legacy)==9 and len(cards)==18

# Capture the actual materialized document before execution to distinguish genuine missing identity from adapter mismatch.
class Captured(RuntimeError):pass
captures=[]
def capture_execute(self,*args,**kwargs):
 captures.append(dict(company_id=kwargs.get('company_id'),documents=[d.to_dict() for d in self.raw_info_store.documents]));raise Captured('stopped before real or synthetic Signal execution')
validator=SignalCandidateValidator(SimpleNamespace(),llm_runner=None)
spec=lib.SignalSpec.from_dict(newdefs['specs'][0]);original=fixtures['by_ref'][spec.ref][0]
controls=[]
def control(name,fixture):
 results={}
 for label,run in [('candidate',lambda:validator._execute_fixture(spec,None,fixture,index=0)),('stable_audit',lambda:lib._audit_deterministic_fixture(spec,fixture,index=0))]:
  count=len(captures)
  try:run()
  except Captured:status='captured_before_Signal'
  except Exception as error:status=f'{type(error).__name__}: {error}'
  else:status='returned_without_Signal'
  materialized=captures[-1] if len(captures)>count else None
  identity=[]
  if materialized:
   for raw in materialized['documents']:
    d=RawInfoDocument.from_dict(raw)
    try:validate_company_fact_document_issuer(d,json.loads(d.content))
    except Exception as exc:identity.append(f'{type(exc).__name__}: {exc}')
    else:identity.append('issuer_binding_valid')
  results[label]=dict(status=status,captured_input=materialized,issuer_checks=identity)
 controls.append(dict(name=name,results=results))
with patch('socket.socket',side_effect=AssertionError('network forbidden')),patch('socket.create_connection',side_effect=AssertionError('network forbidden')),patch.object(lib.SignalExecutor,'execute_batch',capture_execute):
 control('new_approved_sec_company_facts_alias_vs_financials',original)
 canonical=copy.deepcopy(original);canonical['documents'][0]['source_type']='financials';canonical['documents'][0]['metadata']={};control('valid_body_and_canonical_fixture_company_no_metadata',canonical)
 mismatch=copy.deepcopy(original);mismatch['documents'][0]['source_type']='financials';body=json.loads(mismatch['documents'][0]['content']);body['cik']='0000000002';mismatch['documents'][0]['content']=json.dumps(body,sort_keys=True,separators=(',',':'));mismatch['documents'][0]['metadata']={'cik':'0000000002'};control('opaque_audit_alias_erases_canonical_fixture_company_mismatch',mismatch)
 malformed=copy.deepcopy(original);malformed['documents'][0]['source_type']='financials';malformed['documents'][0]['content']={'facts':'not a string'};control('nonstring_content_rejected_by_candidate_but_coerced_by_audit',malformed)
assert controls[0]['results']['candidate']['status']=='captured_before_Signal' and 'outside SignalSpec' in controls[0]['results']['stable_audit']['status']
assert controls[1]['results']['candidate']['issuer_checks']==['issuer_binding_valid'] and 'opaque company has no explicit issuer binding' in controls[1]['results']['stable_audit']['issuer_checks'][0]
assert 'metadata issuer mismatch' in controls[2]['results']['candidate']['issuer_checks'][0] and controls[2]['results']['stable_audit']['issuer_checks']==['issuer_binding_valid']
assert 'content must be a string' in controls[3]['results']['candidate']['status'] and controls[3]['results']['stable_audit']['status']=='captured_before_Signal'
# Meta/status JSON and owning validator policy calculations are pure.
status_card=lib.SignalCard(signal_id=spec.signal_id,version=spec.version,category=spec.category,description=spec.description,execution_type=spec.execution_type,research_status={'technical_status':'admitted','effect_status':'unverified','research_targets':['surge_direction'],'admission_key':'a'*64})
json.loads(json.dumps(status_card.to_dict()));json.loads(json.dumps({'research_status':{spec.ref:dict(status_card.research_status)}}))
policy=SimpleNamespace(validator=validator,_role_work_identity=SignalEvolutionEngine._role_work_identity);policy_hash=SignalEvolutionEngine._technical_validator_hash(policy);assert len(policy_hash)==64
library_tree=ast.parse(library_source);freeze=next(n for n in ast.walk(library_tree) if isinstance(n,ast.FunctionDef) and n.name=='freeze' and n.lineno>1700);assert 'self.audit_capabilities()' in ast.unparse(freeze)
report=dict(status='blocked_before_publication_by_real_legacy_identity_gaps_and_fixture_adapter_inconsistency',authoritative_repo=str(ROOT),prepared_plan_exists=(BASE/'publication/plan.json').exists(),execution_marker_exists=(BASE/'publication/execution-start.json').exists(),legacy_missing_binding_refs=legacy,independent_fixture_adapter_counterexamples=controls,findings=[dict(priority='P1',kind='genuine_missing_fixture_identity',description='All nine historical financial fixture sets contain typed facts without body.cik and metadata.cik. Opaque audit company cannot prove issuer. This must remain rejected; original and cloned old version files must not be filled or guessed. Current fresh freeze performs all18 capability audit and correctly rejects this baseline.'),dict(priority='P1',kind='candidate_to_stable_adapter_contract_drift',description='Candidate uses fixture.company_id, source_types_compatible and string-only content; stable audit hardcodes capability_fixture, uses literal source membership and str(content) coercion. Captured controls prove false rejection, potential issuer-context false acceptance, and malformed-content coercion without invoking a Signal.'),dict(priority='P2',kind='cloned_old_version_protection_gap',description='Driver rechecks original Registry bytes and reconstructs old spec+skill hash, but does not hash-check cloned old versions/tests after promotion. Snapshot identity excludes fixture file bytes. Add explicit old immutable version-file membership/hash checks while allowing only targeted manifests/registry metadata/new-version paths.'),dict(priority='P2',kind='exact_output_envelope_check',description='Driver saves all output cards but should assert exact18 latest refs == input18 with only approved two refs advanced, and exact admission identity/status keys. Freeze already performs capability audit; a duplicate audit is not a substitute for fixing real fixture gaps.')],nonfindings=dict(SignalCard_to_dict_exists=True,all18_metadata_shape_JSON_serializable=True,research_status_JSON_serializable=True,SignalCandidateValidation_asdict_JSON_serializable=True,owning_technical_validator_hash_SimpleNamespace_call_executable=True,owning_policy_hash_shape=policy_hash),permitted_local_fix_boundary='Spec-first align the two fixture materialization adapters on existing company/source/content rules; preserve missing/mismatched issuer rejection, PIT/literal behavior and immutable fixture bytes. Shared pure materialization or minimal congruent adapter logic may be tested with supported aliases/canonical+opaque identity/negative and unavailable cases. No new resource allowance, real source Signal or publication is required for this repair.',remaining_baseline_block='Adapter repair cannot manufacture omitted CIK in the nine old financial versions. Exact18 clone still cannot fresh-freeze after an honest fix. Do not bypass freeze, rewrite clone old-version tests, fake an input snapshot or substitute a different baseline under the old hash. A concrete legally versioned migration/initialization design is needed before S7 can proceed; its scope may require the user design decision stipulated by AGENTS.',history_preservation='Partial prepare cloned files and failed before plan/execute/publication; retain that clone and log as failed precondition evidence. Old source Registry and completed diagnostics remain unchanged.',scope=dict(roles=0,real_source_Signal=0,synthetic_Signal=0,publication=0,original_Registry_writes=0,product_edits=0,network=0,labels=0),correction_to_reviewer_earlier_message='Current SignalRegistry.freeze explicitly invokes audit_capabilities. Earlier shorthand suggesting absent explicit driver audit meant no all18 audit was incorrect; the prepare failure proves the gate runs.')
write('fixture-audit-counterreview-v1.json',report);bindings[str(Path(__file__).resolve())]=hashlib.sha256(Path(__file__).read_bytes()).hexdigest();write('fixture-audit-counterreview-v1-bindings.json',bindings)
print(json.dumps(dict(status=report['status'],legacy_refs=9,adapter_controls=len(controls),Signal_calls=0,report_sha256=hashlib.sha256((OUT/'fixture-audit-counterreview-v1.json').read_bytes()).hexdigest())))
