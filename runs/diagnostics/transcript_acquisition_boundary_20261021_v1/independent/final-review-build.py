"""Seal local transcript boundary evidence using stdlib reads only."""
from pathlib import Path
import ast,hashlib,json,subprocess
ROOT=Path('/Users/l/Project/Recommandation');HERE=Path(__file__).resolve().parent
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
expected={'src/stock_opportunity_agent/data/acquisition.py':'7f7298d90e21b00cfd4fdfd095e116167c20e1136826b23754d1c9a729004270','scripts/run_cold_start_formal.py':'34d6336e3b4649cb05add2ccccfe11e4bce7ee228183d553bd67fec061e1b722'}
assert all(sha(ROOT/p)==h for p,h in expected.items())
rawpaths=['src/stock_opportunity_agent/data/sources/alpha_vantage.py','src/stock_opportunity_agent/data/sources/finnhub.py','src/stock_opportunity_agent/data/sources/state.py','src/stock_opportunity_agent/data/resolution.py','src/stock_opportunity_agent/research/evolution_control.py']
unchanged={}
for path in rawpaths:
 before=subprocess.check_output(['git','show','HEAD:'+path],cwd=ROOT)
 assert before==(ROOT/path).read_bytes(),path
 unchanged[path]=sha(ROOT/path)
invpath=ROOT/'reports/transcript-proof-inventory-20261019.json';inv=json.loads(invpath.read_text())
assert len(inv['records'])==inv['fixed_denominator']==26 and inv['public_content_proofs_accepted']==0
assert sha(invpath)=='c998c06077fc2bed98ea8db29073d6981c00a66fa8974ecdddf3175bcfee8256'
assert all(sha(Path(row['source_path']))==row['file_sha256'] for row in inv['records'])
assert 'Ran 8 tests' in (HERE/'candidate-independent-tests.log').read_text() and (HERE/'candidate-independent-tests.log').read_text().rstrip().endswith('OK')
oldlog=(HERE/'original-verified-independent-tests.log').read_text();assert 'FAILED (failures=9)' in oldlog and '\nERROR:' not in oldlog
files=['test_independent_boundary.py','candidate-independent-tests.log','original-verified-independent-tests.log','original-independent-tests.log','original-acquisition.py.txt','original-882f-acquisition.py.txt','original-run_cold_start_formal.py.txt','before-baseline-binding-test.py.txt','source-only-expectations.json','final-review-build.py']
r={
 'status':'PASS_LOCAL_PROOFLESS_MATERIALIZATION_BOUNDARY_NOT_TRANSCRIPT_QUALIFICATION',
 'candidate_bindings':expected,'unchanged_raw_interface_and_resolver_factory_bindings':unchanged,
 'independent_results':{'test_methods':8,'candidate_passed':8,'exact_old_baseline_passed_methods':3,'exact_old_failed_methods':5,'exact_old_failure_assertions_or_subcases':9,'exact_old_errors':0},
 'confirmed':[
 'All three Alpha transcript aliases and missing-client/identity boundary reject with HISTORICAL_DATA_UNAVAILABLE before provider methods; ad hoc identity proof flags cannot override.',
 'Native generic resolver/factory persist a typed historical gap, not provider_no_data/provider_error. available=False is introspection; first resolve still reserves one provider-level request under existing semantics and repeated same failure is memoized with no further reservation.',
 'Synthetic local eligible transcript is consumable without acquisition, future local source excluded, disabled policy remains external_not_authorized. None is claimed a real public-content proof.',
 'Generic request can still resolve an independently supplied filing fallback; transcript gap does not mean economic absence or disable other source families.',
 'Legacy formal provider date and calendar-quarter-end each previously materialized a partial body as COMPLETE_BODY; candidate returns no DocumentRecord and never calls list/body clients.',
 'Real AlphaVantageClient/FinnhubClient -> ManagedHttpTransport -> RawDataCache -> freshly reopened native cache/client path preserves complete JSON dictionaries and transcript arrays. Only innermost HTTP is fake; neither client nor cache is mocked.',
 'Alpha raw path: one fake HTTP get on initial call, zero on reopened call, ledger fetched/cache_hit. Finnhub list+body: two fake gets then zero, two fetched/two cache_hit. Cache file bytes remain identical on hits; dummy token absent from ledger.',
 'Raw source clients/state, resolver and production factory bytes remain identical to HEAD. Original26 records and inventory remain hash-exact, proofs accepted still0.'
 ],
 'harness_correction':{'first_log':'original-independent-tests.log','cause':'Concurrent writer update occurred between earlier source read and snapshot copy: original-acquisition.py.txt is actually candidate7f729, not old882f. That first Alpha7-green result is not old-source evidence.','corrected_old':'Saved Git HEAD original-882f-acquisition.py.txt is exact882f; legacy original copy is exact4b3. Explicit isolated loaders use those two pinned files; no shared source replacement. Exact old run has9 assertion/subcase failures across5methods.','seal_harness_note':'First stdlib seal check searched ERROR: anywhere and matched DataGapReason.PROVIDER_ERROR enum text inside an expected assertion; corrected to line-anchored unittest ERROR header, original seal log retained. No product/test rerun.', 'candidate_factory':'Candidate temporary factory alias patch supplies the identical native Adapter class; old mode supplies pinned old Adapter to the otherwise unchanged native factory. No provider client/cache/resolve algorithm is mocked.'},
 'limits':['This blocks unsound automatic historical transcript materialization; it neither establishes first-party completion/publication time nor admits any of the original26.','No new proof interface, historical migration, global append, real stage, fresh model/GET/Signal/LabelStore or research claim. Raw HTTP response bytes are not simulated here; complete parsed JSON and native persisted-cache bytes are verified.','Factory credentials absent may still report existing configuration unavailability; external authorization precedence is unchanged.','Guarded fake HTTP tests are local wiring/compatibility evidence, not actual API/provider availability.'],
 'evidence_bindings':[{'path':str(HERE/name),'sha256':sha(HERE/name)} for name in files],
 'original_inventory_binding':{'path':str(invpath),'sha256':sha(invpath)},
 'commands':{'old':'PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src:scripts:tests:. TRANSCRIPT_REVIEW_ORIGINAL=1 python3.12 '+str(HERE/'test_independent_boundary.py'),'candidate':'PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src:scripts:tests:. python3.12 '+str(HERE/'test_independent_boundary.py')}
}
p=HERE/'final-review.json';p.write_text(json.dumps(r,indent=2)+'\n');print(sha(p))
