"""Static named-producer inventory; consumes saved baseline results, runs no tests."""
import ast
import hashlib
import json
from pathlib import Path

REPO = Path(__file__).resolve().parents[4]
OUT = Path(__file__).resolve().parent
ROOT = OUT.parent / 'root'
sha = lambda p: hashlib.sha256(p.read_bytes()).hexdigest()
old = json.loads((ROOT / 'original-failed-selectors-result.json').read_text())
last = json.loads((OUT / 'original-single-selector-layout-result.json').read_text())
source = REPO / 'src/stock_opportunity_agent/research/signal_evolution.py'
assert sha(source) == '23b036dfd4a116dba7518355210df66fefd5f880e69e03a9db63ae911bc4598f'
rows = []
for filename in ('tests/test_signal_evolution_engine.py', 'tests/test_imported_signal_feedback.py'):
    path = REPO / filename
    tree = ast.parse(path.read_text())
    wanted = {s.rsplit('.', 1)[-1] for s in old['selectors'] if filename.split('/')[-1][:-3] in s}
    for method in ast.walk(tree):
        if not isinstance(method, ast.FunctionDef) or method.name not in wanted:
            continue
        for call in ast.walk(method):
            if not (isinstance(call, ast.Call) and isinstance(call.func, ast.Attribute)
                    and isinstance(call.func.value, ast.Name) and call.func.value.id == 'RawInfoDocument'
                    and call.func.attr == 'create'):
                continue
            fields = {k.arg: k.value for k in call.keywords}
            content = fields.get('content')
            numeric = isinstance(content, ast.Call) and isinstance(content.func, ast.Name) and content.func.id == 'sec_company_facts_content'
            rows.append({'file': filename, 'method': method.name, 'line': call.lineno,
                'document_id_expression': ast.unparse(fields['document_id']),
                'company_id_expression': ast.unparse(fields['company_id']),
                'content_producer': 'sec_company_facts_content' if numeric else ast.unparse(content),
                'metadata_declared': 'metadata' in fields,
                'proposed_repair': 'Add metadata={cik: 0000000001} only; retain all original content bytes and assertions.' if numeric else 'No change: unrelated prose is not a numerical positive.'})
helper_path = REPO / 'tests/scheme_evolution_test_support.py'
helper_tree = ast.parse(helper_path.read_text())
helper = next(n for n in ast.walk(helper_tree) if isinstance(n, ast.FunctionDef) and n.name == 'sec_company_facts_content')
assert any(isinstance(n, ast.Dict) and any(isinstance(k, ast.Constant) and k.value == 'cik' and isinstance(v, ast.Constant) and v.value == 1 for k,v in zip(n.keys,n.values)) for n in ast.walk(helper))
numeric_rows = [r for r in rows if r['content_producer'] == 'sec_company_facts_content']
assert len(numeric_rows) == 10 and all(not r['metadata_declared'] for r in numeric_rows)
log = (ROOT / 'original-failed-selectors.log').read_text()
reason = 'SEC Company Facts opaque company has no explicit issuer binding'
assert reason in log
bindings_paths = [source, REPO/'tests/test_signal_evolution_engine.py', REPO/'tests/test_imported_signal_feedback.py', helper_path,
    REPO/'src/stock_opportunity_agent/data/sec_company_facts.py', ROOT/'run_original_failures.py', ROOT/'original-failed-selectors-result.json',
    ROOT/'original-failed-selectors.log', ROOT/'connected-final-result.json', OUT/'original-single-selector-layout-probe.py',
    OUT/'original-single-selector-layout-result.json', OUT/'original-single-selector-layout.log', Path(__file__).resolve()]
record = {
 'scope': 'Read-only static named-producer diagnosis plus preserved native old-module evidence; no new test run, Signal, source/test edits, labels, network or stage operation.',
 'current_source_sha256': sha(source),
 'old_baseline': {'module_sha256': old['original_module_sha256'], 'initial_ten': {'failures':7,'errors':2,'passed':1},
    'initial_imported_selector_error':'Temporary __file__ layout omitted relative signal_library.py; retained unchanged, not a product error.',
    'corrected_single_selector': {'tests':last['tests'],'failures':len(last['failures']),'errors':len(last['errors']),'tripwires':last['tripwires']},
    'corrected_nine_non_regression_outcomes': {'failures':8,'errors':1},
    'separate_real_candidate_regression':'Legacy authored prior brief passed old module, failed initial candidate; fixed by scoped legacy compatibility and now passes.'},
 'producer_inventory': sorted(rows, key=lambda r:(r['file'],r['line'])),
 'minimal_proposal': {'files':['tests/test_signal_evolution_engine.py','tests/test_imported_signal_feedback.py'],
    'named_positive_constructor_sites':10,'engine_methods':8,'engine_sites':9,'imported_methods':1,'imported_sites':1,
    'addition':{'metadata':{'cik':'0000000001'}},
    'body_identity':'Existing helper already serializes body cik=1 canonically.',
    'unchanged':['Body bytes/values/tags/units/periods/clocks','Assertions/expected outcomes','Generic helpers','Released fixtures/Registry','Strict production issuer/PIT/measurement gates','Unrelated prose fixture']},
 'causality': {'native_confirmed':'Saved top-three actionable-target old native result contains validation_failed with exact explicit-issuer-binding error.',
    'static_all_nine':'All nine failed selectors consume named helper-body positives with opaque company aliases and absent metadata; strict source binder requires explicit metadata for opaque companies.',
    'limitation':'Other selector-specific downstream symptoms (including repeated unknown/executed ref) are not individually proven solely caused by metadata. A future authorized metadata-only patch plus the same nine selectors must establish that; do not change assertions or core if any persist.'},
 'bindings':[{'path':str(p),'sha256':sha(p)} for p in bindings_paths]
}
output = OUT / 'remaining-old-fixture-diagnosis.json'
with output.open('x') as f:
    json.dump(record, f, indent=2, sort_keys=True);f.write('\n')
print(json.dumps({'path':str(output),'sha256':sha(output),'numeric_positive_sites':len(numeric_rows),'source_unchanged':sha(source)==record['current_source_sha256']}))
