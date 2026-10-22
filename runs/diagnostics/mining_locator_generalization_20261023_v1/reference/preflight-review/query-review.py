"""Independent local original-source query/noquery compatibility review; no role receive."""
import hashlib
import json
import runpy
from dataclasses import asdict
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
import run_mining_taxonomy_consumer_stage as boundary
from stock_opportunity_agent.data.raw_info import RawInfoDocument, RawInfoStore
from stock_opportunity_agent.research import mining_agent_tools as current

ROOT=Path(__file__).resolve().parents[5]
BASE=ROOT/"runs/diagnostics/mining_locator_generalization_20261023_v1"
OUT=BASE/"reference/preflight-review"
def bind(p):return {"path":str(p),"sha256":hashlib.sha256(p.read_bytes()).hexdigest()}
oldpath=BASE/"preflight-initial-failure/before-mining-agent-tools.py"
old=runpy.run_path(str(oldpath))
rows=[]
with boundary.guards():
 for docno,tag in [("1179","CashFlowsFromUsedInOperatingActivities"),("0770","NetCashProvidedByUsedInOperatingActivities"),("0671","NetCashProvidedByUsedInOperatingActivities")]:
  p=ROOT/f"runs/diagnostics/reviewed_gpre_capture_snapshot_20261021_v1/stage/snapshot/documents/{docno}.json"
  source=p.read_bytes(); d=RawInfoDocument.from_dict(json.loads(source)); case=SimpleNamespace(case_id="opaque-review",company_id=d.company_id,prediction_time=d.available_at)
  args={"source_families":("sec_company_facts",),"max_documents":1,"case_ref":"opaque-review"}
  store=RawInfoStore(documents=(d,))
  before=old["fetch_case_evidence"](store,case,**args)
  now=current.fetch_case_evidence(store,case,**args)
  assert asdict(before)==asdict(now),"noquery regression"
  targeted=current.fetch_case_evidence(store,case,query=tag,**args)
  facts=[f for f in targeted.facts if f.concept==tag]
  originals=[x for x in json.loads(d.content)["facts"] if x["tag"]==tag]
  assert len(facts)==len(originals)==2
  assert all(f.exact_span in d.content and json.loads(f.exact_span) in originals for f in facts)
  assert {json.dumps(json.loads(f.exact_span),sort_keys=True) for f in facts}=={json.dumps(x,sort_keys=True) for x in originals}
  assert all(f.content_hash==d.content_hash and f.unit==json.loads(f.exact_span)["unit"] and f.taxonomy==json.loads(f.exact_span)["taxonomy"] and f.value==str(json.loads(f.exact_span)["value"]) for f in facts)
  prior_by_ref={f.fact_ref:asdict(f) for f in now.facts}
  assert all(asdict(f)==prior_by_ref[f.fact_ref] for f in targeted.facts if f.fact_ref in prior_by_ref)
  before_explicit=old["fetch_case_evidence"](store,case,query=tag,**args)
  assert p.read_bytes()==source
  rows.append({"source":bind(p),"noquery_unchanged":True,"old_target_query_operand_count":sum(f.concept==tag for f in before_explicit.facts),"current_target_query_operand_count":len(facts),"exact_whole_original_rows":True,"common_ref_identity_unchanged":True,"before_fact_count":len(before.facts),"current_targeted_fact_count":len(targeted.facts)})
result={"state":"local_query_projection_original_source_review_passed","sources":rows,"old_code":bind(oldpath),"new_code":bind(ROOT/"src/stock_opportunity_agent/research/mining_agent_tools.py"),"limits":"Local original-source/noquery projection only; not fresh author or preflight budget success.","external_API_GET":0,"role_receives":0}
p=OUT/"query-review-result.json"
with p.open("x") as f:json.dump(result,f,ensure_ascii=False,indent=2);f.write("\n")
print(json.dumps(result,ensure_ascii=False))
