"""Read exact source JSON with stdlib only; freeze private pre-answer expectations."""
from pathlib import Path
from datetime import datetime, timezone
from decimal import Decimal
import hashlib, json, re

REPO = Path('/Users/l/Project/Recommandation')
OUT = REPO/'runs/diagnostics/gpre_native_initial_20261021_v1/independent-preflight'
BASE = REPO/'runs/diagnostics/reviewed_gpre_capture_snapshot_20261021_v1/stage'
def sha_bytes(value): return hashlib.sha256(value).hexdigest()
def binding(path):
    raw=path.read_bytes()
    return {'path':str(path.relative_to(REPO)), 'sha256':sha_bytes(raw), 'bytes':len(raw)}
def read(path): return json.loads(path.read_text())
def write(name, value):
    p=OUT/name
    if p.exists(): raise RuntimeError('immutable independent output exists: '+name)
    p.write_text(json.dumps(value,ensure_ascii=False,sort_keys=True,indent=2)+'\n')
    return binding(p)

docs={str(n):read(BASE/f'snapshot/documents/{n:04}.json') for n in (1513,1514,1706,1779)}
basic=read(BASE/'basic-info.json')
manifest=read(BASE/'snapshot/reviewed_snapshot.json')
assert len(manifest['documents'])==1780
cutoff='2025-05-30T00:00:00+00:00'
source_bindings=[binding(BASE/'snapshot/reviewed_snapshot.json'),binding(BASE/'basic-info.json')]
for n,d in docs.items():
    assert d['company_id']=='cik_0001309402'
    assert datetime.fromisoformat(d['available_at'])<=datetime.fromisoformat(cutoff)
    assert sha_bytes(d['content'].encode())==d['content_hash']
    source_bindings.append(binding(BASE/f'snapshot/documents/{int(n):04}.json'))
raw_aliases=[]
for n in ('1513','1514'):
    text=docs[n]['content']
    for field in ('EntityRegistrantName','TradingSymbol'):
        for m in re.finditer(r'dei:'+field+r'"[^>]*>([^<]+)<',text):
            value=m.group(1)
            assert value in ('GREEN PLAINS INC.','GPRE')
            start=m.start(1)
            raw_aliases.append({'document_id':docs[n]['document_id'],'source_field':'dei:'+field,
                'exact_text':value,'start':start,'end':start+len(value),'offset_unit':'unicode_codepoints'})
assert {r['exact_text'] for r in raw_aliases}=={'GREEN PLAINS INC.','GPRE'}
prices=json.loads(docs['1706']['content'])
assert len(prices)==171
selected=sorted((p for p in prices if p['as_of_date']<'2025-05-30'),key=lambda p:p['as_of_date'])[-5:]
mean=sum(Decimal(str(p['adjusted_close'])) for p in selected)/Decimal(5)
anchor={'source_document_id':docs['1706']['document_id'],'method':'mean_last_5_complete_adjusted_closes_strictly_before_prediction_time',
 'full_raw_bar_count':len(prices),'actual_first_bar':prices[0]['as_of_date'],'actual_last_bar':prices[-1]['as_of_date'],
 'trading_dates':[p['as_of_date'] for p in selected],'adjusted_close_literals':[str(p['adjusted_close']) for p in selected],
 'mean_adjusted_close_decimal':str(mean),'doubling_threshold_decimal':str(mean*2),
 'recent_close_literal':str(selected[-1]['adjusted_close']),'recent_close_date':selected[-1]['as_of_date'],
 'check_only_not_payload':True,'caveat':'Native core must compute independently from complete PIT market documents. This check does not authenticate historical adjustment/split/provider truth. Metadata requested start is not actual bar coverage.'}
visibility=[]
for req in basic['model']['requests']:
    row={k:v for k,v in req.items() if k not in ('projections','omitted_context_markers')}
    row['omission_marker_count']=len(req['omitted_context_markers'])
    row['projections']=[{'projection_id':p['projection_id'],'document_id':p['document_id'],'available_at':p['available_at'],
        'exact_text_sha256':sha_bytes(p['exact_text'].encode()),'exact_text_chars':len(p['exact_text'])} for p in req['projections']]
    visibility.append(row)
assert sum(len(r['projections']) for r in visibility)==17
facts=[
 {'topic':'business','source_projection_indices':[1,2,4,5,6,7,9,10], 'boundary':'Two reportable segments: ethanol production and agribusiness/energy services. Storage/transport/product detail may be stated only as actually visible. Intersegment activity is eliminated in consolidated results; segment totals are not consolidated revenue.'},
 {'topic':'Q1 reported table','source_projection_indices':[0,11], 'period':'three months ended March 31, 2025 versus 2024','unit':'USD thousands', 'reported_consolidated_revenue':[601515,597214],'reported_consolidated_cost_of_goods_sold':[598476,588847],'reported_gross_margin_amount':[3039,8367], 'boundary':'Do not confuse segment external/intersegment/including-intersegment figures or gross-margin dollars with percentage ratio. These values are permitted when exact current visible table/header supports them; none is a required answer.'},
 {'topic':'annual revenue classification','source_projection_indices':[14], 'period':'twelve months ended December 31, 2024','unit':'USD thousands','ASC606_subtotal':162973,'ASC815_subtotal':2295823,'combined_total':2458796,'boundary':'ASC606 subtotal is not whole-company annual revenue. Preserve classification and eliminations; do not annualize the Q1 table.'},
 {'topic':'operating comparability','source_projection_indices':[7,10], 'boundary':'Visible narrative identifies Birmingham terminal sale September 2024, Fairmont idling January 2025 and early-2025 restructuring/cost initiatives. Disclosure of initiatives is not realized savings or proof of later restart.'},
 {'topic':'risk versus outcome','source_projection_indices':[3,10,12,13], 'boundary':'Tariff/export, commodity/supply-demand, regulatory/low-carbon and strategic-alternatives uncertainties can support qualitative risks/hypotheses. Forward-looking assumptions and merger benefits are not guarantees or demonstrated future results.'},
 {'topic':'historical financial snippet','request_id':'orientation.v1.financial_facts','boundary':'Old snippet contains shares outstanding 65,399,452 as of May 5, 2025 and accounts payable 154,817,000 end Dec 31,2024 /102,305,000 end Mar31,2025. Preserve stock/flow/as-of/unit differences. New typed projection may expose more/different complete rows; assess against actual new wire, never hidden whole document.'}
]
oracle={
 'schema':'gpre-initial-source-only-independent-oracle-v1','frozen_at_utc':datetime.now(timezone.utc).isoformat(),
 'timing':'Before any new H_init model answer. No subsequent role output read, no native bootstrap/Store/helper/model executed by this script.',
 'case':{'case_id':'cik_0001309402:20250530','company_id':'cik_0001309402','prediction_time':cutoff},
 'fixed_denominator':{'native_bootstrap_and_H_init_case':1},
 'sources':source_bindings,'source_alias_proofs':raw_aliases,'view_admitted_documents':1780,
 'historical_visibility':{'basis':'Saved old source-stage BasicInfo, not the new bootstrap request','projection_count':17,
  'canonical_model_utf8_bytes':len(json.dumps(basic['model'],ensure_ascii=False,sort_keys=True,separators=(',',':')).encode()),
  'requests':visibility,'new_visibility_requirement':'Before role dispatch compare actual native model context. If producer changes visibility, bind a pre-answer visibility addendum; never require hidden old/new facts, handfill cards or treat the historical count as native proof.'},
 'source_fact_boundaries_not_required_answer':facts,'private_anchor_crosscheck':anchor,
 'acceptance':[
  'Actual execute_information_plan must use the declared manual/default InformationPlan and qualified PIT source view. Source acquisition plan is not an accepted research Plan.',
  'Core, not wrapper or oracle, computes baseline/control cards from complete market sources. Compare private independent baseline only after native preflight; evaluation_anchor/computed_metrics remain control data, never numerical issuer beliefs/contradictions/evidence.',
  'Every returned factual belief, contradiction and support citation must be grounded in exact actual visible BasicInfo projection identity/text/PIT. Metadata dates/forms alone are not quoted issuer evidence.',
  'Hypotheses are uncertain propositions, not fabricated facts, guarantees, observed returns or causal/benefit claims. No prescribed hypothesis, count quota or need wording is imposed.',
  'Needs request only material facts absent from actual visible BasicInfo and the returned state, potentially disclosed by cutoff. May ask then-disclosed future schedule; may not require post-cutoff actuals/results.',
  'News unavailable/external_not_authorized and projection/source omissions are coverage limits, never evidence of no events/no debt/no catalyst or proof the omitted fact exists. Preserve actual partial/omission flags.',
  'Period/issuer/unit/classification and integer versus thousands must stay exact; no Q1 annualization, partial revenue replacement, currentness beyond source availability or inference from mere document presence.',
  'No six downstream Signal results are required or injected. This stage establishes H_init only; no genuine routing ownership, Reflect semantics, Predictor or benefit is established.',
  'Canonical source-derived legal name/ticker/CIK must be masked in actual outgoing wire. Native paths must not leak identity through actor handoff: neutral exact inbox copy, neutral outbox, raw copy byte equal, no issuer/oracle/answer in role message.',
  'Original raw, native acceptance/correction/mechanical disposition, persisted accepted state, reread evidence and final stop must be audited separately. Schema pass or hash alone is not semantic pass.',
  'Frozen ceiling: at most two independent local author responses including one native structured correction; each reservation <=131072, case <=256000. Stop immediately after accepted InitialBoundary; no Signals/Predictor/labels/GET or complete successor.'
 ],
 'required_native_preflight_evidence':['exact current Plan/bundle/model/lineage','native core evaluation_context/anchor/computed_metrics','actual masked pre-egress and request-ready/journal reservations','source-derived identity aliases and neutral handoff plan','read-only guards for tail selection/Signal/Predictor/labels/network/global writes','actual accepted H_init raw→parser→persist→reread and bounded terminal restore after later authorization'],
 'limits':['Full source documents are oracle context; model obligations depend exclusively on actual visible projections.','Historical public clocks are accepted source-policy boundaries, not a new API-vintage or primary-audit guarantee.','No source-status or omission marker is evidence; source presence does not prove every fact read.','No accepted prior, H_init, ownership or fresh capability is claimed by this source-only freeze.']}
write('pre-answer-source-oracle.json',oracle)
write('source-oracle-freeze-result.json',{'status':'source_only_oracle_frozen_native_preflight_required','oracle':binding(OUT/'pre-answer-source-oracle.json'),'script':binding(Path(__file__)), 'production_helpers_executed':0,'stores_opened':0,'models':0,'network':0,'labels':0})
print(json.dumps({'oracle':binding(OUT/'pre-answer-source-oracle.json'),'price_crosscheck':anchor,'source_count':len(source_bindings),'aliases':raw_aliases},ensure_ascii=False,indent=2))
