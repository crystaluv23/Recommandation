"""Independent local origin review; no model, network, labels, or stage calls."""
import ast
from copy import deepcopy
from dataclasses import asdict, replace
from datetime import datetime, timedelta, timezone
import hashlib
import json
from pathlib import Path
import random
import socket
import subprocess
from types import SimpleNamespace
import unittest
from unittest.mock import patch

ROOT = Path.cwd()
OUT = ROOT / 'runs/diagnostics/mining_query_navigation_20261023_v1/independent'
network_attempts = []
def no_network(*args, **kwargs):
    network_attempts.append(repr(args[:1])); raise AssertionError('network forbidden')
socket.socket.connect = no_network
socket.create_connection = no_network
from stock_opportunity_agent.research import evolution_core as core
from stock_opportunity_agent.research import mining_agent_tools as tools
from stock_opportunity_agent.research.mining_controller import LabelAwareMiningController, InvalidMiningAction
from stock_opportunity_agent.data.raw_info import RawInfoDocument, RawInfoStore
from stock_opportunity_agent.research.stage_contracts import json_bytes

NOW = datetime(2025, 1, 10, tzinfo=timezone.utc)
CASE = SimpleNamespace(company_id='independent_fixture', case_id='independent-case', prediction_time=NOW,
                       ground_truth=SimpleNamespace(is_surge=False))
checks = 0
def digest(value): return hashlib.sha256(value.encode()).hexdigest()
def old_functions(path, names, namespace):
    raw = subprocess.check_output(['git', 'show', 'f0f81fb1:' + path], text=True)
    tree = ast.parse(raw)
    selected = ast.Module(body=[n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name in names], type_ignores=[])
    exec(compile(selected, 'independent-git-f0-oracle', 'exec'), namespace)
    return digest(raw)
ns = dict(vars(core))
old_source_hash = old_functions('src/stock_opportunity_agent/research/evolution_core.py',
    {'_h3_document_visible_text', '_query_relevant_excerpt'}, ns)
legacy = ns['_query_relevant_excerpt']
legacy_tools = dict(vars(tools)); legacy_tools['_query_relevant_excerpt'] = legacy
old_functions('src/stock_opportunity_agent/research/mining_agent_tools.py', {'fetch_case_evidence'}, legacy_tools)
legacy_fetch = legacy_tools['fetch_case_evidence']
def doc(raw, kind='company_news', title='', name='ind-source', owner=CASE.company_id):
    return RawInfoDocument.create(document_id=name, company_id=owner, source_type=kind,
        published_at=NOW, available_at=NOW, content=raw, metadata={'title': title})
def controller(docs, pairs=None):
    return LabelAwareMiningController(store=RawInfoStore(documents=docs), model=object(),
        case_pairs=pairs or [('case-one', CASE)], measurable_evidence_manifest={}, signal_catalog=[],
        seed='discovery', heavy_action_limit=50, light_action_limit=50, browse_limit=50)
def fetch(c, query='controls procedures', refs=None, maximum=40):
    return c._execute_fetch({'action':'fetch_evidence', 'case_refs':refs or ['case-one'],
        'source_families':list(c.available_source_families), 'query':query, 'max_documents':maximum})

class IndependentReview(unittest.TestCase):
    def origins(self, d, query='controls procedures', size=600):
        global checks
        actual = core._query_relevant_excerpt_with_origins(d, query=query, max_chars=size)
        self.assertEqual(actual[:2], legacy(d, query=query, max_chars=size))
        self.assertEqual(actual[:2], core._query_relevant_excerpt(d, query=query, max_chars=size))
        for f in actual[2]['fragments']:
            self.assertTrue(0 <= f['raw_start'] < f['raw_end'] <= len(d.content))
            self.assertLessEqual(f['raw_end'] - f['raw_start'], 4000)
            self.assertTrue(actual[2]['selected_start'] <= f['projection_start'] < f['projection_end'] <= actual[2]['selected_end'])
        checks += 1
        return actual

    def test_01_generated_legacy_oracle(self):
        rng = random.Random(4047)
        alphabet = ['controls', 'procedures', ' ', '\n', '\t', '\r', '\u2003', '"', '\\', '/', '\b', '\f', '𝄞', '&amp;', '<p>x</p>', 'é', '弱', 'inventory']
        for i in range(90):
            text = ''.join(rng.choice(alphabet) for _ in range(rng.randrange(1, 70)))
            payload = {'content':text, 'nested':{'body':'decoy controls'}, 'body':'body ' + text,
                       'summary':rng.choice([12, {'dict':'controls'}, ['procedures'], '', None, False]), 'title':'headline controls'}
            raw = json.dumps(payload, ensure_ascii=i % 2 == 0)
            if i % 4 == 0: raw = raw[:-1] + ',"\\u0062ody":"last body controls procedures"}'
            for source in ('company_news', 'filing', 'transcript'):
                d = doc(raw, source, title='virtual controls \u2003 procedures')
                for q in (None, '', 'controls procedures', 'unmatched'):
                    for size in (1, 17, 85, 600): self.origins(d, q, size)

    def test_02_json_origin_exactness(self):
        raw = '{"body":"discarded", "nested":{"body":"decoy"},"\\u0062ody":"BODY \\ud834\\udd1e \\u2003 \\\\u0061 \\"quote\\" controls procedures","title":"TITLE controls"}'
        d = doc(raw)
        text, _, origin = self.origins(d)
        pieces = [raw[f['raw_start']:f['raw_end']] for f in origin['fragments']]
        self.assertEqual(len(pieces), 2)
        self.assertTrue(pieces[0].startswith('TITLE'))
        self.assertTrue(pieces[1].startswith('BODY'))
        self.assertNotIn('discarded', ''.join(pieces)); self.assertNotIn('decoy', ''.join(pieces))
        self.assertGreater(origin['fragments'][0]['raw_start'], origin['fragments'][1]['raw_start'])
        self.assertTrue(origin['mapping_complete'])
        for f in origin['fragments']:
            self.assertEqual(' '.join(json.loads('"' + raw[f['raw_start']:f['raw_end']] + '"').split()), text[f['projection_start']:f['projection_end']])
        for raw in ('{"body":"old", "\\u0062ody":42}', '{"body":"old", "body":null}', '{"body":"old", "body":{"x":"controls"}}'):
            _, _, origin = self.origins(doc(raw))
            self.assertFalse(origin['fragments']); self.assertFalse(origin['mapping_complete'] if '42' in raw or 'x' in raw else origin['unmapped_nonspace_chars'])

    def test_03_hidden_and_title_cannot_reanchor(self):
        raw = '<script>' + 'controls procedures ' * 1000 + '</script><p>REAL controls</p><script>' + 'x' * 30000 + '</script><p>procedures TAIL</p>'
        d = doc(raw, 'filing', title='controls procedures')
        _, _, origin = self.origins(d)
        self.assertEqual([raw[f['raw_start']:f['raw_end']] for f in origin['fragments']], ['REAL controls', 'procedures TAIL'])
        self.assertGreater(origin['unmapped_nonspace_chars'], 0)
        self.assertFalse(self.origins(doc('<script>controls procedures</script>', 'filing', title='controls procedures'))[2]['fragments'])
        for raw in ('{"body":"controls"} trailing', '["controls", "procedures"]', '{bad:controls}', 'controls &amp; procedures'):
            for kind in ('company_news', 'filing'): self.origins(doc(raw, kind))

    def test_04_raw_limit_and_escape_pairs(self):
        for count in (333, 334, 590):
            raw = '{"body":"' + '\\ud834\\udd1e' * count + ' controls procedures"}'
            _, _, origin = self.origins(doc(raw))
            self.assertTrue(origin['mapping_complete'])
            self.assertGreaterEqual(len(origin['fragments']), 2)
            for f in origin['fragments']:
                piece = raw[f['raw_start']:f['raw_end']]
                self.assertNotEqual(piece[-1:], '\\')
                json.loads('"' + piece + '"')

    def test_05_fetch_canonical_unchanged(self):
        for d in (doc('{"body":"controls procedures", "title":"news"}'), doc('<p>controls procedures</p>', 'filing', title='metadata')):
            for q in (None, '', ' ', 'controls'):
                args = dict(source_families=[d.source_type], query=q, max_documents=1, case_ref='case-one')
                store = RawInfoStore(documents=[d]); actual = tools.fetch_case_evidence(store, CASE, **args); old = legacy_fetch(store, CASE, **args)
                for field in ('documents','facts','narrative_events','excluded_by_limits','query_coverage','unread_same_source','request'):
                    self.assertEqual(getattr(actual, field), getattr(old, field))
                for r in actual.query_navigation:
                    self.assertEqual(r['case_ref'], 'case-one'); self.assertEqual(r['content_hash'], d.content_hash)
                    self.assertEqual(r['raw_span_sha256'], digest(d.content[r['raw_start']:r['raw_end']]))

    def test_06_working_view_cross_step_read_authority_and_binding(self):
        d = doc('<p>controls procedures liquidity</p>', 'filing')
        c = controller([d]); fetch(c)
        first = deepcopy(c._model_view()['query_navigation']['items'])
        self.assertEqual(c.materialization_evidence(), {}); self.assertEqual(c._narrative_reads, 0)
        predicate = {'modality':'narrative','source_families':['filing'], 'semantic_condition':'controls'}
        event_ref = next(iter(c._events))
        with self.assertRaises(InvalidMiningAction): c._validate_narrative_predicate(predicate, {event_ref})
        self.assertNotIn(first[0]['navigation_ref'], c.ledger.evidence_refs())
        c._execute('inspect_manifest', {'action':'inspect_manifest'})
        self.assertEqual(c._model_view()['query_navigation']['items'], first)
        fetch(c); self.assertEqual(c._model_view()['query_navigation']['counts']['available'], 1)
        fetch(c, 'liquidity'); self.assertEqual(c._model_view()['query_navigation']['counts']['available'], 2)
        self.assertEqual(c._heavy_used, 3); self.assertEqual(c._browse_used, 0)
        row = first[0]
        c._execute_read_span({'document_ref':row['document_ref'], 'offset':row['raw_start'], 'length':row['read_length']})
        self.assertEqual(c._browse_used, 1); self.assertEqual(c._narrative_reads, 1)
        c._validate_narrative_predicate(predicate, {event_ref})
        result = c._documents[row['document_ref']]
        changed = doc('<p>controls procedures changed</p>', 'filing')
        c._documents[row['document_ref']] = replace(result, documents=(changed,))
        # All aliases must reference the changed source snapshot for lookup.
        c._documents[event_ref] = c._documents[row['document_ref']]
        self.assertFalse(c._model_view()['query_navigation']['items'][0]['source_snapshot_matches'])

    def test_07_scope_pit_and_whole_page(self):
        docs = [doc('controls procedures ' + str(i), 'filing', name='src-' + str(i)) for i in range(25)]
        other = SimpleNamespace(**vars(CASE)); other.case_id = 'other-case'
        c = controller(docs, [('case-one',CASE), ('case-two',other)])
        fetch(c, refs=['case-one','case-two'])
        page = c._model_view()['query_navigation']
        self.assertEqual(page['counts']['available'], 50)
        self.assertLessEqual(len(page['items']),12); self.assertLessEqual(json_bytes(page['items']),8000)
        self.assertFalse(page['selection_is_exhaustive']); self.assertEqual(c._heavy_used,1)
        self.assertEqual({r['case_ref'] for r in c.ledger.entries[0].coverage['query_navigation']}, {'case-one','case-two'})
        wrong = doc('controls procedures', 'filing', owner='other-owner')
        future = replace(docs[0], available_at=NOW+timedelta(days=1))
        result = tools.fetch_case_evidence(RawInfoStore(documents=[wrong,future]), CASE, source_families=['filing'], query='controls', max_documents=5)
        self.assertFalse(result.documents); self.assertFalse(result.query_navigation)

if __name__ == '__main__':
    OUT.mkdir(exist_ok=True)
    suite = unittest.defaultTestLoader.loadTestsFromTestCase(IndependentReview)
    run = unittest.TextTestRunner(verbosity=2).run(suite)
    summary = {'tests':run.testsRun,'failures':len(run.failures),'errors':len(run.errors),
        'legacy_oracle_comparisons':checks,'network_attempts':network_attempts,'old_full_core_sha256':old_source_hash,
        'scope':'synthetic fixtures only, source-local projection/fetch/controller methods; no API/LabelStore/stage execution'}
    print(json.dumps(summary, ensure_ascii=True, indent=2))
    (OUT / 'summary-attempt-2.json').write_text(json.dumps(summary, indent=2))
    raise SystemExit(not run.wasSuccessful())
