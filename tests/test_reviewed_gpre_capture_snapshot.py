"""Temporary native source versions; never prepare or append actual GPRE records."""
from contextlib import ExitStack
from copy import deepcopy
from dataclasses import replace
import json
from pathlib import Path
import socket
from tempfile import TemporaryDirectory
from unittest import TestCase
from unittest.mock import patch

import diagnose_reviewed_gpre_capture_snapshot as diagnostic
from stock_opportunity_agent.artifacts import canonical_json_hash
from stock_opportunity_agent.data.raw_info import RawInfoDocument, RawInfoStore
from stock_opportunity_agent.data.resolution import RawInfoDocumentRef, RawInfoRequest, RawInfoResolution, _deduplicate_documents
from stock_opportunity_agent.data.reviewed_snapshot import materialize_reviewed_snapshot, open_raw_info_store
from stock_opportunity_agent.models import ValidationError
from tests.test_reviewed_companyfacts_profile import CompanyFactsProfileFixture, write_bound
from tests.test_reviewed_frozen_case_inputs import copy_group


class CaptureStageFixture:
    """Keep the full real normalizer/profile while using two isolated accessions."""

    def __init__(self, root):
        self.root = root
        self.fixture = f = CompanyFactsProfileFixture(root/'source')
        self.old_records = [p.to_dict() for p in f.products]
        self.base = root/'base'; self.base.mkdir()
        self.output = root/'new-stage'
        # A same-content legacy original has a different complete acquisition record.
        old = f.products[1]
        self.conflicting_path = Path(f.find_original(old.document_id)['path'])
        write_bound(self.conflicting_path, replace(old, metadata={**old.metadata,'old_capture':True}).to_dict())
        f.review['records'] = f.review['records'][:1]
        review_path = f.save()
        self.review = json.loads(review_path.read_bytes())
        write_bound(self.base/'source-review.json',self.review)
        self.view = materialize_reviewed_snapshot(review_path,self.base/'snapshot')
        self.input_binding = write_bound(self.base/'input_manifest.json', {
            'source_review':diagnostic._binding(self.base/'source-review.json'), 'reviewed_source_snapshot':self.view})
        self.diagnosis = root/'old-diagnosis'/'result.json'
        write_bound(self.diagnosis, {'retained':True})
        self.case = {'case_id':'cik_0000000001:20250731','products':[],'normalization':f.normalization_binding}
        for product in f.products:
            saved = write_bound(root/'saved-products'/(product.document_id+'.json'),product.to_dict())
            collision = diagnostic.preappend._collision(product,f.oracle)
            self.case['products'].append({**collision,'product':saved,'profile_preverified':True})
        self.consumer_case = {'case_id':self.case['case_id'],'company_id':f.item['company_id'],
                              'prediction_time':f.selection['available_at_through']}
        self.identity = {'cik':f.item['cik'],'ticker':f.item['symbol']}
        self.groups = [copy_group(root,name) for name in ('default_v6','latest_v12')]
        self.data = diagnostic.preappend._bindings([f.normalization_binding,f.cache_binding,f.raw_binding,
            diagnostic._binding(self.base/'source-review.json'),*diagnostic.financial._tree(self.base/'snapshot'),
            *[p['product'] for p in self.case['products']],
            *[m['original_record'] for p in self.case['products'] for m in p['matches']]])

    def authorities(self, output):
        return (self.review,self.fixture.oracle,self.case,self.consumer_case,self.identity,self.groups,self.data,self.view)

    def context(self):
        stack = ExitStack()
        for name,value in (('PRODUCTS',2),('CONFLICTS',1),('BASE_DOCS',1),('BASE_ROWS',1),('BASE',self.base),('DIAGNOSIS',self.diagnosis),
                           ('AUTHORITIES',{self.base/'input_manifest.json':self.input_binding['sha256']})):
            stack.enter_context(patch.object(diagnostic,name,value))
        stack.enter_context(patch.object(diagnostic,'_authorities',side_effect=self.authorities))
        return stack


class GpreCaptureStageTests(TestCase):
    def fixture(self, root):
        return CaptureStageFixture(root)

    def test_prepare_native_full_set_and_only_collision_subset_without_global_store(self):
        with TemporaryDirectory() as directory:
            f = self.fixture(Path(directory).resolve())
            before = diagnostic.financial._tree(f.fixture.oracle)
            with f.context(), patch.object(RawInfoStore,'__init__',side_effect=AssertionError('global constructor')):
                plan = diagnostic.prepare(f.output)
            self.assertEqual(plan['products_count'],2)
            self.assertEqual(len(plan['products']),2)
            self.assertEqual(len(plan['selected_ids']),1)
            normalized = diagnostic._read_bound(plan['normalization'])[1]
            self.assertEqual(normalized['normalized_at'],f.fixture.normalization['normalized_at'])
            self.assertEqual(normalized['identity_policy'],'raw-info-capture-v1')
            self.assertEqual(len(normalized['expected_products']),2)
            self.assertEqual(diagnostic.financial._tree(f.fixture.oracle),before)
            with f.context(), self.assertRaisesRegex(diagnostic.ReviewedSourceRejected,'must be new'):
                diagnostic.prepare(f.output)

    def test_execute_actual_append_replay_view_two_groups_and_basic_info(self):
        with TemporaryDirectory() as directory:
            f = self.fixture(Path(directory).resolve())
            before = diagnostic.financial._tree(f.fixture.oracle)
            with f.context():
                plan = diagnostic.prepare(f.output)
                result = diagnostic.execute(f.output,plan['plan_hash'])
            self.assertEqual(result['status'],'completed')
            self.assertEqual(len(result['append_receipts']),1)
            self.assertTrue(result['append_receipts'][0]['inserted'])
            self.assertFalse(result['append_receipts'][0]['same_capture_replay_inserted'])
            diagnostic._check(before)
            view = result['reviewed_source_snapshot']
            store = open_raw_info_store(view['root'],reviewed_snapshot=view)
            self.assertEqual(len(store.documents),2)
            review = diagnostic._read_bound(result['source_review'])[1]
            self.assertEqual(canonical_json_hash(review['records'][:1]),canonical_json_hash(f.review['records']))
            for group in f.groups:
                rows = diagnostic._read(f.output/(group['name']+'.json'))['resolutions']
                self.assertEqual([r['signal_ref'] for r in rows],group['refs'])
                self.assertEqual(len(rows),18)
            self.assertEqual(len(diagnostic._read(f.output/'basic-info.json')['bundle']['requests']),4)
            selections = diagnostic._read(f.output/'consumer-selection-evidence.json')
            self.assertEqual(len(selections['default_v6']),18)
            self.assertEqual(len(selections['latest_v12']),18)
            financial = [r for r in selections['basic_info'] if r['financial_source_request']]
            self.assertEqual(len(financial),1)
            self.assertEqual(financial[0]['status'],'latest_q1_selected')
            scope = diagnostic._read(f.output/'visible-financial-scope.json')
            self.assertIn(result['append_receipts'][0]['document_id'],scope['q1_source_ids'])
            with f.context(), self.assertRaises(FileExistsError):
                diagnostic.execute(f.output,plan['plan_hash'])

    def test_complete_set_and_typed_profile_failure_precede_any_append(self):
        with TemporaryDirectory() as directory:
            f = self.fixture(Path(directory).resolve())
            with f.context():
                bad = deepcopy(f.case); bad['products'].pop()
                with self.assertRaisesRegex(diagnostic.ReviewedSourceRejected,'denominator'):
                    diagnostic._derive(bad,f.review,f.fixture.oracle)
                docs,_,normalized,_ = diagnostic._derive(f.case,f.review,f.fixture.oracle)
                normalized['normalized_at'] = '2020-01-01T00:00:00+00:00'
                binding = write_bound(f.root/'bad-normalization.json',normalized)
                with self.assertRaises(diagnostic.ReviewedSourceRejected):
                    diagnostic._qualify(docs,normalized,binding,diagnostic.frozen._aware(f.consumer_case['prediction_time']))
                normalized['normalized_at'] = f.fixture.normalization['normalized_at']
                normalized['expected_products'][0]['canonical_record_hash'] = '0'*64
                binding = write_bound(f.root/'bad-set.json',normalized)
                with self.assertRaises(diagnostic.ReviewedSourceRejected):
                    diagnostic._qualify(docs,normalized,binding,diagnostic.frozen._aware(f.consumer_case['prediction_time']))

    def test_bound_source_drift_is_terminal_before_global_constructor(self):
        with TemporaryDirectory() as directory:
            f = self.fixture(Path(directory).resolve())
            with f.context(): plan = diagnostic.prepare(f.output)
            f.conflicting_path.write_text(f.conflicting_path.read_text()+' ')
            with f.context(), patch.object(diagnostic.RawInfoStore,'__init__',side_effect=AssertionError('global constructor')):
                with self.assertRaises(diagnostic.ReviewedSourceRejected):
                    diagnostic.execute(f.output,plan['plan_hash'])
            self.assertTrue((f.output/'failure.json').exists())
            self.assertFalse((f.output/'append-receipts').exists())
            with f.context(), self.assertRaises(FileExistsError):
                diagnostic.execute(f.output,plan['plan_hash'])

    def test_cross_namespace_capture_canonical_drift_rejects_without_changing_legacy(self):
        with TemporaryDirectory() as directory:
            f = self.fixture(Path(directory).resolve())
            with f.context():
                _,selected,_,_ = diagnostic._derive(f.case,f.review,f.fixture.oracle)
                doc = selected[0]
                # A corrupt differently typed JSON record cannot masquerade as that ID.
                bad = doc.to_dict(); bad['metadata']['retrospective_api_extraction'] = 1
                write_bound(f.fixture.oracle/'other'/doc.company_id/(doc.document_id+'.json'),bad)
                with self.assertRaisesRegex(diagnostic.ReviewedSourceRejected,'capture ID'):
                    diagnostic._derive(f.case,f.review,f.fixture.oracle)
            self.assertEqual(json.loads(f.conflicting_path.read_bytes())['metadata']['old_capture'],True)

    def test_same_content_versions_dedup_and_real_source_only_tripwires(self):
        with TemporaryDirectory() as directory:
            f = self.fixture(Path(directory).resolve())
            original = f.fixture.products[0]
            captures = [original.as_capture(),replace(original,metadata={**original.metadata,'other_capture':True}).as_capture()]
            kept,duplicates = _deduplicate_documents([original,*captures])
            self.assertEqual(len(kept),1); self.assertEqual(len(duplicates),2)
            store = RawInfoStore(documents=(original,*captures))
            self.assertEqual(len(store.documents),3)
            self.assertEqual(len(_deduplicate_documents(store.search(original.company_id,as_of=original.available_at))[0]),1)
            from stock_opportunity_agent.cases.label_store import LabelStore
            from stock_opportunity_agent.signal_library import SignalExecutor
            import run_minimal_rounds
            for function in (lambda: socket.socket(),lambda: LabelStore.record(None,'x'),
                             lambda: SignalExecutor.execute_batch(None,()),lambda: run_minimal_rounds.prepare()):
                with diagnostic.frozen._source_only(), self.assertRaises(diagnostic.ReviewedSourceRejected):
                    function()

    def test_existing_exact_selected_capture_rejects_fresh_prepare_before_append(self):
        with TemporaryDirectory() as directory:
            f = self.fixture(Path(directory).resolve())
            selected = f.fixture.products[1].as_capture()
            self.assertTrue(RawInfoStore(f.fixture.oracle).append(selected))
            with f.context(), self.assertRaisesRegex(diagnostic.ReviewedSourceRejected,'already exists'):
                diagnostic.prepare(f.output)
            self.assertTrue((f.output/'preparation-failure.json').exists())
            self.assertFalse((f.output/'plan.json').exists())

    def test_visible_q1_does_not_pass_when_actual_consumer_selected_only_old_period(self):
        with TemporaryDirectory() as directory:
            f = self.fixture(Path(directory).resolve())
            old,q1 = f.fixture.products
            store = RawInfoStore(documents=(old,q1))
            request = RawInfoRequest(request_id='financial',description='Reported facts',source_types=('sec_company_facts',))
            resolution = RawInfoResolution(request=request,status='resolved',documents=(RawInfoDocumentRef.from_document(old),))
            evidence = diagnostic._selected_scope(resolution,store,q1.available_at)
            self.assertEqual(evidence['status'],'gap_latest_q1_not_selected')
            self.assertEqual(evidence['latest_q1_source_ids'],[])
            self.assertEqual(evidence['selected_documents'][0]['document_id'],old.document_id)
            selected = replace(resolution,documents=(RawInfoDocumentRef.from_document(q1),))
            self.assertEqual(diagnostic._selected_scope(selected,store,q1.available_at)['status'],'latest_q1_selected')

    def test_destinations_and_invalid_execute_plan_reject_before_any_filesystem_write(self):
        with TemporaryDirectory() as directory:
            f = self.fixture(Path(directory).resolve())
            before = diagnostic.financial._tree(f.root)
            with f.context():
                for protected in (f.fixture.oracle,f.base,f.diagnosis.parent):
                    output = protected/'new-child'
                    with self.subTest(output=output), self.assertRaisesRegex(diagnostic.ReviewedSourceRejected,'overlaps'):
                        diagnostic.prepare(output)
                    self.assertFalse(output.exists())
                    with self.assertRaises(diagnostic.ReviewedSourceRejected):
                        diagnostic.execute(output,'0'*64)
                    self.assertFalse(output.exists())
                arbitrary = f.root/'no-plan'
                with self.assertRaises(FileNotFoundError):
                    diagnostic.execute(arbitrary,'0'*64)
                self.assertFalse(arbitrary.exists())
            self.assertEqual(diagnostic.financial._tree(f.root),before)
            with f.context():
                plan = diagnostic.prepare(f.output)
                plan['output'] = str(f.output/'wrong-stage')
                plan['plan_hash'] = canonical_json_hash({k:v for k,v in plan.items() if k!='plan_hash'})
                write_bound(f.output/'plan.json',plan)
                before = diagnostic.financial._tree(f.root)
                with self.assertRaisesRegex(diagnostic.ReviewedSourceRejected,'scope/hash'):
                    diagnostic.execute(f.output,plan['plan_hash'])
                self.assertFalse((f.output/'execution-start.json').exists())
                self.assertEqual(diagnostic.financial._tree(f.root),before)
