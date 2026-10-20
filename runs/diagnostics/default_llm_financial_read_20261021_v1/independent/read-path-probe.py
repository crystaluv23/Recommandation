"""Pure source/rank/projection inspection, no Store/Signal/model/transport execution."""
from pathlib import Path
from types import SimpleNamespace
import hashlib,json
from stock_opportunity_agent.data.raw_info import RawInfoDocument
from stock_opportunity_agent.data.resolution import _request_query_tokens,_document_query_hit_count
from stock_opportunity_agent.signal_library import SignalSpec,LLMSignalBatchInput
from stock_opportunity_agent.research.evolution_signal_roles import _single_llm_signal_projection,StructuredLLMSignalRunner
R=Path('/Users/l/Project/Recommandation');D=R/'runs/diagnostics/default_llm_financial_read_20261021_v1/independent';S=R/'runs/diagnostics/reviewed_gpre_capture_snapshot_20261021_v1/stage/snapshot';read=lambda p:json.loads(Path(p).read_text());sha=lambda p:hashlib.sha256(Path(p).read_bytes()).hexdigest();bind=lambda p:{'path':str(Path(p).resolve()),'sha256':sha(p)}
refs=R/'runs/cold_start/minimal_rounds_v182_integrated/signals/financial/cash_to_current_liabilities_ratio/versions/v1';spec=SignalSpec.from_dict(read(refs/'spec.json'));skill=(refs/'skill.md').read_text();assert spec.ref=='cash_to_current_liabilities_ratio:v1'
source_manifest=read(S/'reviewed_snapshot.json');paths={x['document_id']:(S/x['path'],x['sha256']) for x in source_manifest['documents']};selection_path=R/'runs/diagnostics/measurement_input_selection_20261021_v1/default_v6.json';row=next(x for x in read(selection_path)['rows'] if x['signal_ref']==spec.ref)
selected=row['resolution']['documents'];q1id=next(x for x in paths if x.startswith('rawcap:v1:64c9e4'));assert q1id not in {x['document_id'] for x in selected}
tokens=_request_query_tokens(SimpleNamespace(query=row['resolution']['request']['query']));facts=[];documents=[];sourcebindings=[]
for docid in [x['document_id'] for x in selected]+[q1id]:
 p,h=paths[docid];assert sha(p)==h;doc=read(p);assert doc['document_id']==docid and doc['company_id']=='cik_0001309402';body=json.loads(doc['content']);schema=body.get('schema_version','nested');sourcebindings.append(bind(p))
 relevant=[]
 if isinstance(body.get('facts'),list):
  for f in body['facts']:
   if f.get('tag') in ['CashAndCashEquivalentsAtCarryingValue','LiabilitiesCurrent']:
    relevant.append({k:f.get(k) for k in ['tag','unit','start','end','value']})
 elif isinstance(body.get('facts'),dict):
  for taxonomy,concepts in body['facts'].items():
   if not isinstance(concepts,dict):continue
   for tag in ['CashAndCashEquivalentsAtCarryingValue','LiabilitiesCurrent']:
    for unit,records in concepts.get(tag,{}).get('units',{}).items():
     relevant.extend({'tag':tag,'unit':unit,'start':f.get('start'),'end':f.get('end'),'value':f.get('val')} for f in records)
 facts.append({'document_id':docid,'selected':docid!=q1id,'source_type':doc['source_type'],'body_schema':schema,'available_at':doc['available_at'],'query_hit_count':_document_query_hit_count(SimpleNamespace(content=doc['content']),tokens),'content_bytes':len(doc['content'].encode()),'latest_concept_end':{tag:max((f['end'] for f in relevant if f['tag']==tag and f['end']),default=None) for tag in ['CashAndCashEquivalentsAtCarryingValue','LiabilitiesCurrent']},'q1_named_facts':[f for f in relevant if f['end']=='2025-03-31']})
 if docid!=q1id:documents.append(RawInfoDocument.from_dict(doc))
assert len(documents)==10 and row['resolution']['coverage']['eligible_document_count']==57
# This is the existing pure projection producer on the already selected10,
# not SignalExecutor.prepare_inputs/execute and not an actual sent role request.
item=LLMSignalBatchInput(spec,tuple(documents),skill);projection,lineage=_single_llm_signal_projection(item);runner=object.__new__(StructuredLLMSignalRunner);runner.identity_cases={};payload=runner._batch_payload((item,),projection,lineage,__import__('datetime').datetime.fromisoformat('2025-05-30T00:00:00+00:00'),budget_trimmed=False)
assert q1id not in json.dumps(payload) and all(x['document_id'] in {d.document_id for d in documents} for x in projection)
proof={'exact_ref':spec.ref,'source_ranking_evidence':facts,'selected_count':10,'eligible_count':57,'unselected_count':47,'actual_input_only_resolution_status':row['resolution']['status'],'actual_coverage':row['resolution']['coverage'],'q1_named_facts_exist_in_qualified_source':bool(facts[-1]['q1_named_facts']),'projection_inspection':{'kind':'pure existing projection over previously selected10; not actual transmitted wire','payload_keys':list(payload),'context_contract':payload['context_contract'],'projection_count':len(projection),'projected_source_count':len({x['document_id'] for x in projection}),'projected_source_ids':sorted({x['document_id'] for x in projection}),'fact_context_projection_count':sum('fact_context' in x for x in projection),'q1_unselected_source_not_addressed':True,'original_resolution_coverage_not_in_payload':True,'no_catalog_fetch_read_refs_keys':not any(k in payload for k in ['document_catalog','fetch_documents','read_refs'])},'bindings':{'spec':bind(refs/'spec.json'),'skill':bind(refs/'skill.md'),'prior_input_rows':bind(selection_path),'reviewed_snapshot':bind(S/'reviewed_snapshot.json'),'inspected_documents':sourcebindings},'limits':['No new model/GET/LabelStore/Store/Signal application/prepare_inputs/fullprepare/stage reentry.','No claim that the old skill actually misused accession prefixes or produced a wrong measurement; no LLM output was obtained.','Q1 source membership is necessary data availability evidence, not proof of model-readable compatibility or correct measurement.','Generic selection and inner projection are separate truncation layers. Existing edge repair addresses only selected source lineage, not the47unselected source documents.']}
for x in sourcebindings:assert sha(x['path'])==x['sha256']
p=D/'read-path-results.json';p.write_text(json.dumps(proof,ensure_ascii=False,indent=2)+'\n');print('PASS read-only evidence',sha(p));print('selected rank hits',[x['query_hit_count'] for x in facts[:-1]],'Q1',facts[-1]['query_hit_count']);print('projection',proof['projection_inspection'])
