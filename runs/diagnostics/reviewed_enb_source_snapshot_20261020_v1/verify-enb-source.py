"""Verify the new ENB SEC-only view through existing production store/resolver APIs."""
from pathlib import Path
from datetime import datetime,timedelta
import argparse,hashlib,json,subprocess,sys,os,socket,ssl
REPO=Path('/Users/l/Project/Recommandation')
ROOT=Path(__file__).resolve().parent
attempts=[]
def forbidden(*args,**kwargs):
    attempts.append('socket')
    raise AssertionError('Network is forbidden in the ENB source-only diagnostic')
socket.socket=forbidden
from stock_opportunity_agent.artifacts import canonical_json_hash
from stock_opportunity_agent.data.raw_info import RawInfoDocument
from stock_opportunity_agent.data.reviewed_snapshot import materialize_reviewed_snapshot,open_raw_info_store
from stock_opportunity_agent.data.resolution import EvidenceResolver,RawInfoRequest
from stock_opportunity_agent.models import ValidationError

def read(path):return json.loads(path.read_text())
def bind(path):return {'path':str(path.resolve()),'sha256':hashlib.sha256(path.read_bytes()).hexdigest()}
def document_identity(doc):return {'document_id':doc.document_id,'content_hash':doc.content_hash,'record_hash':canonical_json_hash(doc.to_dict()),'available_at':doc.available_at.isoformat()}
def identities(store):return sorted((document_identity(d) for d in store.documents),key=lambda d:d['document_id'])
def child():
    inputs=read(ROOT/'input_manifest.json');binding=inputs['reviewed_source_snapshot'];store=open_raw_info_store(binding['root'],reviewed_snapshot=binding)
    print(json.dumps({'store_type':type(store).__name__,'binding':store.binding,'acquisition_allowed':store.acquisition_allowed,'documents':identities(store)},sort_keys=True))
def verify():
    report=REPO/'reports/enb-reviewed-source-inputs-20261020.json';review=read(report);inputs=read(ROOT/'input_manifest.json');binding=read(ROOT/'snapshot_binding.json');assert binding==inputs['reviewed_source_snapshot'];assert bind(report)==inputs['source_review'];assert review['manifest_hash']==canonical_json_hash({k:v for k,v in review.items() if k!='manifest_hash'});assert inputs['fixed_source_denominator']==3
    original_paths=[Path(row['original_record']['path']) for row in review['records']];proof_paths={Path(proof['artifact']['path']) for row in review['records'] for proof in row['proofs']};proof_paths.add(Path(review['oracle_identity']['path']));before={str(p):bind(p)['sha256'] for p in original_paths+list(proof_paths)}
    originals={row['document_id']:RawInfoDocument.from_dict(read(Path(row['original_record']['path']))) for row in review['records']}
    store=open_raw_info_store(binding['root'],reviewed_snapshot=binding);worker=store.snapshot();assert type(worker) is type(store) and worker.binding==store.binding and store.acquisition_allowed is False and worker.acquisition_allowed is False
    expected=sorted((document_identity(d) for d in originals.values()),key=lambda d:d['document_id']);assert identities(store)==identities(worker)==expected
    env=dict(os.environ);env['PYTHONPATH']=str(REPO/'src')+':'+str(REPO/'scripts')+':'+str(REPO);env['PYTHONDONTWRITEBYTECODE']='1'
    restarted=subprocess.run([sys.executable,str(Path(__file__).resolve()),'--restart-child'],cwd=REPO,env=env,text=True,capture_output=True,check=True);restarted=json.loads(restarted.stdout);assert restarted['documents']==expected and restarted['binding']==binding and restarted['acquisition_allowed'] is False and restarted['store_type']==type(store).__name__
    cutoff=datetime.fromisoformat(review['scope']['as_of']);resolver=EvidenceResolver(worker)
    request=RawInfoRequest('enb-fixed-sec-only','Read only the fixed admitted ENB SEC originals.',('filing',),lookback_days=730,max_documents=3)
    resolution=resolver.resolve(request,company_id='cik_0000895728',identity={},as_of=cutoff,include_context=False);loaded=resolver.load_documents(resolution,as_of=cutoff);assert resolution.status=='resolved' and len(loaded)==3 and {d.document_id:d.to_dict() for d in loaded}=={k:d.to_dict() for k,d in originals.items()}
    roundtrip=type(resolution).from_dict(resolution.to_dict());reloaded=resolver.load_documents(roundtrip,as_of=cutoff);assert {d.document_id:d.to_dict() for d in reloaded}=={k:d.to_dict() for k,d in originals.items()}
    pit=[]
    for doc in originals.values():
        before_time=doc.available_at-timedelta(seconds=1)
        try:worker.load(doc.document_id,as_of=before_time)
        except ValidationError:rejected=True
        else:rejected=False
        assert rejected and worker.load(doc.document_id,as_of=doc.available_at)==doc
        assert doc.document_id not in {d.document_id for d in worker.search(doc.company_id,as_of=before_time)}
        assert doc.document_id in {d.document_id for d in worker.search(doc.company_id,as_of=doc.available_at)}
        current=resolver.resolve(request,company_id=doc.company_id,identity={},as_of=doc.available_at,include_context=False)
        assert doc.document_id in {d.document_id for d in resolver.load_documents(current,as_of=doc.available_at)}
        assert store.append(doc) is False and worker.append(doc) is False
        pit.append({'document_id':doc.document_id,'available_at':doc.available_at.isoformat(),'before_one_second_rejected':True,'exact_instant_load_search_and_resolver':True,'exact_replay_added':False})
    reopened=open_raw_info_store(binding['root'],reviewed_snapshot=binding);assert identities(reopened)==expected
    after={str(p):bind(p)['sha256'] for p in original_paths+list(proof_paths)};assert before==after
    code=[*sorted((REPO/'src/stock_opportunity_agent/data').rglob('*.py')), REPO/'src/stock_opportunity_agent/artifacts.py', REPO/'src/stock_opportunity_agent/models.py']
    out={'schema_version':'reviewed-enb-source-snapshot-diagnostic-v1','scope':'Only three fixed ENB SEC originals. Existing production materialization/store/restart/worker/resolver used; not a complete default InformationPlan run or new model semantic evidence.','input_manifest_hash':canonical_json_hash(inputs),'reviewed_source_snapshot':binding,'source_review':bind(report),'fixed_source_denominator':3,'admitted_documents':expected,'actual_loader_restart':restarted,'worker_type_preserved':True,'worker_explicit_binding_preserved':True,'worker_acquisition_allowed':False,'resolver_exact_three':True,'resolver_reload_exact_three':True,'resolution':resolution.to_dict(),'PIT_and_idempotence':pit,'snapshot_reopen_exact_three':True,'source_and_proof_bindings_before':before,'source_and_proof_bindings_after':after,'original_records_and_proofs_unchanged':True,'code_bindings':[bind(p) for p in code],'diagnostic_script':bind(Path(__file__)),'all_requested_source_boundary_checks_passed':True,'network_attempts':attempts,'external_api_calls':0,'model_calls':0,'new_anchors':0,'full48_preflight_or_execution':False,'source_qualification_not_model_semantic_pass':True,'limits':['No foreign-form20-F/40-F/6-K claim: ENB elects domestic forms.','CAD annual/interim units and explicitUSD notes remain original; consumers still require exact-unit interpretation.','No qualified ENB market baseline/CompanyFacts JSON, full defaultprefix or deterministic secfacts Signal claim.','Actual future orientation projection visibility remains a separate frozen stage.']}
    target=ROOT/'result.json'
    assert not target.exists(),'Preserve prior diagnostic execution; use a new final result if code binding changes'
    target.write_text(json.dumps(out,indent=2,ensure_ascii=False)+'\n')
    print(json.dumps({k:v for k,v in out.items() if k in ['all_requested_source_boundary_checks_passed','fixed_source_denominator','input_manifest_hash','network_attempts','model_calls','external_api_calls','reviewed_source_snapshot']},indent=2))
if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--restart-child',action='store_true');args=parser.parse_args();child() if args.restart_child else verify()
