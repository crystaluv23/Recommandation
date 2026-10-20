"""Temporary proof/manifest controls for the explicit source-only completion executor."""
from copy import deepcopy
from dataclasses import replace
import json
from pathlib import Path
import sys
import tempfile
from unittest import TestCase
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import diagnose_reviewed_frozen_source_completion as completion
from stock_opportunity_agent.data.raw_info import RawInfoDocument, RawInfoStore
from stock_opportunity_agent.data.reviewed_snapshot import ReviewedSourceRejected, materialize_reviewed_snapshot, open_raw_info_store
from tests.test_reviewed_sec_response_profile import SecResponseFixture, bound, write
from tests.test_reviewed_companyfacts_profile import CompanyFactsProfileFixture, write_bound


class FrozenSourceCompletionTests(TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.base = Path(temporary.name)
        self.fixture = SecResponseFixture(self.base / 'sec', linked=False)
        self.fixture.save()
        self.case = {'case_id':'case', 'company_id':self.fixture.company, 'prediction_time':'2025-07-31T00:00:00+00:00'}
        self.key = completion._target_key('operating', 'case', self.fixture.accession)
        self.targets = {self.key:{'case_id':'case','retained_target':{'accession':self.fixture.accession}}}
        body = next(p for p in self.fixture.proofs if p['kind']=='sec_static_archive_body_response')
        self.semantic = {'records':[{'case_id':'case','accession':self.fixture.accession,'document_id':self.fixture.document.document_id,
            'content_hash':self.fixture.document.content_hash,'content_scope':'complete_interim_operating_report','qualified':True,
            'body_binding':body['raw_response'],'reason':'Read actual business/MD&A/statement sections and coherent report end.',
            'review_read_scope':'selected_sections_partial_facts'}]}
        self.candidate = {'document':bound(self.fixture.original),'target_keys':[self.key],
            'proof_profile':'sec_filing_response_acceptance_v1','proofs':self.fixture.proofs,'reason':'Exact fixture whole report.',
            'semantic_review':write(self.base/'semantic.json',self.semantic),'semantic_target':{'case_id':'case','accession':self.fixture.accession}}
        self.dispositions = {self.key:{'reason':'Bound report qualified; facts only partially read.','candidate_ids':[self.fixture.document.document_id]}}

    def qualify(self, candidates=None, targets=None, dispositions=None, cases=None):
        return completion._qualify([self.candidate] if candidates is None else candidates,
            self.targets if targets is None else targets,self.dispositions if dispositions is None else dispositions,
            [self.case] if cases is None else cases,self.fixture.oracle)

    def test_native_proof_qualified_record_materializes_worker_and_restart_without_relabel(self):
        documents = self.qualify()
        self.assertEqual(documents[self.fixture.document.document_id].to_dict(),self.fixture.document.to_dict())
        binding = materialize_reviewed_snapshot(self.fixture.save(), self.base/'view')
        for store in (open_raw_info_store(binding['root'],reviewed_snapshot=binding),
                open_raw_info_store(binding['root'],reviewed_snapshot=binding).snapshot()):
            self.assertEqual(store.documents[0].to_dict(),self.fixture.document.to_dict())

    def test_semantic_flags_cannot_substitute_for_exact_case_body_original_and_source_binding(self):
        variants = [('case_id','different'),('content_hash','0'*64),('document_id','other'),('qualified',False),
            ('content_scope','cover_only'),('body_binding',bound(self.fixture.base/'root.raw')),('review_read_scope','')]
        for field,value in variants:
            with self.subTest(field=field):
                review=deepcopy(self.semantic);review['records'][0][field]=value
                candidate={**self.candidate,'semantic_review':write(self.base/'bad-semantic.json',review)}
                with self.assertRaises(ReviewedSourceRejected):self.qualify([candidate])

    def test_unknown_unpersisted_targets_stay_dispositions_not_fake_originals(self):
        unknown=completion._target_key('operating','case','unfetched')
        targets={**self.targets,unknown:{'case_id':'case','retained_target':{'accession':'unfetched'}}}
        dispositions={**self.dispositions,unknown:{'candidate_ids':[],'reason':'Whole body not retained.'}}
        self.assertEqual(len(self.qualify(targets=targets,dispositions=dispositions)),1)
        with self.assertRaises(ReviewedSourceRejected):self.qualify(targets=targets)
        with self.assertRaises(ReviewedSourceRejected):self.qualify(dispositions={self.key:{'candidate_ids':[],'reason':'Omitted actual candidate'}})

    def test_wrong_exact_type_native_identity_and_early_cutoff_still_reject(self):
        wrong=replace(self.fixture.document,source_type='10-k')
        candidate={**self.candidate,'document':write(self.base/'wrong.json',wrong.to_dict())}
        with self.assertRaises(ReviewedSourceRejected):self.qualify([candidate])
        early={**self.case,'prediction_time':'2025-05-05T19:59:59+00:00'}
        with self.assertRaises(ReviewedSourceRejected):self.qualify(cases=[early])
        bad=deepcopy(self.candidate);bad['semantic_target']['accession']='other'
        with self.assertRaises(ReviewedSourceRejected):self.qualify([bad])

    def test_same_id_different_canonical_global_record_is_rejected_before_append(self):
        original=self.fixture.document
        other=RawInfoDocument.create(document_id=original.document_id,company_id=original.company_id,source_type='news',
            published_at=original.published_at,available_at=original.available_at,content='different retained original',metadata=original.metadata)
        write(self.fixture.oracle/'news'/other.company_id/(other.document_id+'.json'),other.to_dict())
        with self.assertRaises(ReviewedSourceRejected):self.qualify()

    def financial_targets(self):
        fixture=CompanyFactsProfileFixture(self.base/'financial')
        fixture.save()
        case={'case_id':'financial','company_id':fixture.item['company_id'],'normalization':fixture.normalization_binding,
            'products':[{'document_id':d.document_id,'product':fixture.find_original(d.document_id),'collision':False,'profile_preverified':True} for d in fixture.products]}
        stage={'outcomes':{'financial':[case],'market':[],'operating':[]}}
        return fixture,stage,completion._targets(stage)

    def test_financial_subset_keeps_complete_expected_set_and_explicit_unknown_member(self):
        fixture,stage,targets=self.financial_targets()
        document=fixture.products[0];key=completion._target_key('financial','financial',document.document_id)
        candidate={'document':fixture.find_original(document.document_id),'target_keys':[key],
            'proof_profile':'sec_companyfacts_filed_next_utc_day_v1','proofs':fixture.row(document)['proofs'],'reason':'Exact native subset, full expected set retained.'}
        dispositions={k:{'candidate_ids':[document.document_id] if k==key else [],'reason':'Explicit subset/full denominator.'} for k in targets}
        cases=[{'case_id':'financial','company_id':fixture.item['company_id'],'prediction_time':'2025-07-31T00:00:00+00:00'}]
        actual=completion._qualify([candidate],targets,dispositions,cases,fixture.oracle)
        self.assertEqual(list(actual),[document.document_id])
        self.assertEqual(len(fixture.normalization['expected_products']),2)
        broken=deepcopy(stage);broken['outcomes']['financial'][0]['products'].pop()
        with self.assertRaises(ReviewedSourceRejected):completion._targets(broken)
        targets[key]['product']['collision']=True
        with self.assertRaises(ReviewedSourceRejected):completion._qualify([candidate],targets,dispositions,cases,fixture.oracle)

    def test_cross_case_and_proof_drift_fail_on_next_qualification_not_memo_reused(self):
        self.qualify()
        (self.fixture.base/'body.raw').write_bytes(b'changed')
        with self.assertRaises(ReviewedSourceRejected):self.qualify()
        candidate={**self.candidate,'target_keys':[self.key,'market|other|*']}
        targets={**self.targets,'market|other|*':{'case_id':'other','retained_variants':[]}}
        dispositions={**self.dispositions,'market|other|*':{'candidate_ids':[self.fixture.document.document_id],'reason':'Wrong case'}}
        with self.assertRaises(ReviewedSourceRejected):self.qualify([candidate],targets,dispositions)

    def test_preflight_failure_records_terminal_attempt_without_opening_any_store(self):
        output=self.base/'attempt';output.mkdir()
        with patch.object(completion,'_verified_plan',side_effect=ReviewedSourceRejected('fixture preflight failure')) as verify, \
                patch.object(RawInfoStore,'__init__',side_effect=AssertionError('store must not open')):
            with self.assertRaises(ReviewedSourceRejected):completion.execute(output,'fixturehash')
            self.assertEqual(verify.call_count,1)
            self.assertTrue((output/'execution-start.json').is_file())
            self.assertTrue(json.loads((output/'failure.json').read_text())['terminal'])
            with self.assertRaises(FileExistsError):completion.execute(output,'fixturehash')
            self.assertEqual(verify.call_count,1)

    def test_temp_native_two_registry_input_consumers_keep_every_ref_and_partial_basic_info(self):
        from tests.test_reviewed_frozen_case_inputs import copy_group
        binding=materialize_reviewed_snapshot(self.fixture.save(),self.base/'consumer-view')
        groups=[copy_group(self.base,name) for name in ('default_v6','latest_v12')]
        projection={'cases':[self.case],'identities':{self.fixture.company:{'cik':self.fixture.cik,'ticker':'FIXTURE'}}}
        output=self.base/'consumers'
        with completion.frozen._source_only():
            summaries=completion._consume(output,binding,projection,groups)
        self.assertEqual(set(summaries),{'default_v6','latest_v12'})
        for group in groups:
            saved=json.loads((output/group['name']/'case.json').read_text())
            self.assertEqual([row['signal_ref'] for row in saved['exact_signal_input_resolutions']],group['refs'])
            self.assertEqual(len(saved['exact_signal_input_resolutions']),18)
            self.assertEqual(saved['summary']['denominator'],18)
        self.assertEqual(len(json.loads((output/'basic-info/case.json').read_text())['bundle']['requests']),4)

    def test_new_review_scope_describes_original40_both_groups_and_preserves_old_rows(self):
        output=self.base/'scope-producer';output.mkdir()
        old_review={'scope':{'purpose':'Fixed15 sources and exact-v12 only','company_ids':['old']},
            'records':[{'document_id':'preserved-old-row','reason':'verbatim old evidence'}]}
        old_copy=deepcopy(old_review)
        cases=[{**self.case,'case_id':'case'+str(i)} for i in range(40)]
        projection={'cases':cases,'identities':{self.fixture.company:{'cik':self.fixture.cik}}}
        loaded=({'candidates':[self.candidate],'target_dispositions':self.dispositions},projection,old_review,
            self.fixture.oracle,{self.fixture.document.document_id:self.fixture.document},[],[])
        # Run only the actual review producer. Storage, proof reloading and all
        # view/consumer work are fake here; the existing temporary original is read.
        class NoOpStore:
            def __init__(self,root): pass
            def append(self,document): return False
            def load(self,document_id): return self_document
        self_document=self.fixture.document
        with patch.object(completion,'_verified_plan',return_value=({'plan_hash':'fixture'},loaded)), \
                patch.object(completion,'RawInfoStore',NoOpStore), \
                patch.object(completion,'materialize_reviewed_snapshot',side_effect=ReviewedSourceRejected('stop before view')), \
                patch.object(completion,'_consume',side_effect=AssertionError('consumer must not run')):
            with self.assertRaisesRegex(ReviewedSourceRejected,'stop before view'):
                completion.execute(output,'fixture')
        review=json.loads((output/'source-review.json').read_text())
        self.assertEqual(review['records'][:len(old_copy['records'])],old_copy['records'])
        self.assertEqual(old_review,old_copy)
        self.assertEqual(review['scope']['company_ids'],[self.fixture.company])
        self.assertIn('Original40 fixed cases',review['scope']['purpose'])
        self.assertIn('both exact v6/v12 input-only',review['scope']['purpose'])
        self.assertNotIn('Fixed15',review['scope']['purpose'])

    def test_semantic_carrier_is_exact_managed_body_or_actual_response_body_never_other_proof(self):
        for managed in (False, True):
            with self.subTest(managed=managed):
                fixture=SecResponseFixture(self.base/('managed' if managed else 'gzip-exhibit'),
                    linked=not managed,exhibit=not managed,compression=None if managed else 'gzip')
                fixture.save()
                proofs=deepcopy(fixture.proofs)
                if managed:
                    body={'kind':'sec_static_archive_body','endpoint':fixture.body_url,
                        'expected_content_hash':fixture.document.content_hash,
                        'artifact':write(fixture.base/'body-cache.json',{'endpoint':fixture.body_url,'body':fixture.content})}
                    acceptance={**fixture.root_proof,'kind':'sec_submissions_acceptance'}
                    proofs=[body,acceptance]
                else:
                    body=next(p for p in proofs if p['kind']=='sec_static_archive_body_response')
                exact=body['artifact' if managed else 'raw_response']
                semantic=deepcopy(self.semantic)
                semantic['records'][0].update(document_id=fixture.document.document_id,content_hash=fixture.document.content_hash,
                    body_binding=exact,content_scope='complete_interim_operating_report' if managed else 'whole_annual_AIF')
                candidate={**self.candidate,'document':bound(fixture.original),'proofs':proofs,
                    'proof_profile':'sec_archive_acceptance_v1' if managed else 'sec_filing_exhibit_response_v1',
                    'semantic_review':write(fixture.base/'semantic.json',semantic)}
                dispositions={self.key:{'candidate_ids':[fixture.document.document_id],'reason':'Exact carrier positive.'}}
                actual=completion._qualify([candidate],self.targets,dispositions,[self.case],fixture.oracle)
                self.assertEqual(list(actual),[fixture.document.document_id])
                wrong=[p['artifact'] for p in proofs if p is not body]
                wrong += [bound(fixture.base/'body.raw')] if managed else [body['artifact'],
                    next(p['raw_response'] for p in proofs if p['kind']=='sec_parent_primary_response')]
                for index,binding in enumerate(wrong):
                    with self.subTest(managed=managed,wrong=index):
                        changed=deepcopy(semantic);changed['records'][0]['body_binding']=binding
                        bad={**candidate,'semantic_review':write(fixture.base/'wrong-semantic.json',changed)}
                        with self.assertRaises(ReviewedSourceRejected):
                            completion._qualify([bad],self.targets,dispositions,[self.case],fixture.oracle)

    def test_rehashed_actual_body_carrier_still_requires_complete_decoded_content_and_hash(self):
        changed=b'<html>Different full body, same case and declared semantic content hash.</html>'
        path=self.fixture.base/'body.raw';path.write_bytes(changed)
        entry=next(r for r in self.fixture.receipt['requests'] if r['name']=='body')
        entry.update(raw_sha256=bound(path)['sha256'],bytes=len(changed))
        body=next(p for p in self.fixture.proofs if p['kind']=='sec_static_archive_body_response')
        body['raw_response']=bound(path)
        self.fixture.save()
        self.semantic['records'][0]['body_binding']=bound(path)
        self.candidate['semantic_review']=write(self.base/'changed-semantic.json',self.semantic)
        with self.assertRaisesRegex(ReviewedSourceRejected,'whole body/content hash'):
            completion._semantic(self.candidate,self.fixture.document,'case')


class FrozenSourceCompletionCodeBindingTests(TestCase):
    """Freeze real helper dependencies using only patched temporary bundle inputs."""

    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.base = Path(temporary.name)

    def frozen(self, directory):
        helper = directory / 'scripts/diagnose_reviewed_frozen_source_snapshot.py'
        owner = directory / 'spec/scripts/diagnose_reviewed_frozen_source_snapshot.md'
        market = directory / 'spec/src/stock_opportunity_agent/data/reviewed_market_profile.md'
        for path in (helper, owner, market):
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text('Unchanged local dependency: ' + path.name)
        bundle = directory / 'bundle.json'
        write(bundle, {'fixture': 'no actual candidates, oracle, registry or source scope'})
        output = (directory / 'freeze').resolve()
        loaded = ({}, {}, {'oracle_identity': {'fixture': 'not opened'}}, directory / 'unused-oracle', {}, [], [])
        return helper, owner, market, bundle, output, loaded

    def test_preappend_helper_owner_and_market_contract_are_frozen_before_reload(self):
        helper, owner, market, bundle, output, loaded = self.frozen(self.base)
        with patch.object(completion.preappend, '__file__', str(helper)), \
                patch.object(completion.preappend, 'REPO', self.base), \
                patch.object(completion.frozen, '_code_bindings', return_value=[]), \
                patch.object(completion, '_load_bundle', return_value=loaded) as load, \
                patch.object(RawInfoStore, '__init__', side_effect=AssertionError('no store in freeze fixture')):
            plan = completion.prepare(bundle, output)
            bindings = {item['path']: item['sha256'] for item in plan['code_bindings']}
            for dependency in (helper, owner, market):
                self.assertEqual(bindings.get(str(dependency.resolve())), bound(dependency)['sha256'])
            verified, actual = completion._verified_plan(output, plan['plan_hash'])
            self.assertEqual(verified, plan)
            self.assertEqual(actual, loaded)
            self.assertEqual(load.call_count, 2)

    def test_each_runtime_helper_or_contract_drift_rejects_before_bundle_reload_or_store(self):
        for index in range(3):
            with self.subTest(dependency=('preappend_code', 'preappend_spec', 'market_profile')[index]):
                directory = self.base / str(index)
                helper, owner, market, bundle, output, loaded = self.frozen(directory)
                with patch.object(completion.preappend, '__file__', str(helper)), \
                        patch.object(completion.preappend, 'REPO', directory), \
                        patch.object(completion.frozen, '_code_bindings', return_value=[]), \
                        patch.object(completion, '_load_bundle', return_value=loaded) as load, \
                        patch.object(RawInfoStore, '__init__', side_effect=AssertionError('store must not open')):
                    plan = completion.prepare(bundle, output)
                    dependency = (helper, owner, market)[index]
                    dependency.write_text(dependency.read_text() + '\nChanged after freeze')
                    with self.assertRaisesRegex(ReviewedSourceRejected, 'bound source changed'):
                        completion._verified_plan(output, plan['plan_hash'])
                    self.assertEqual(load.call_count, 1, 'drift must reject before bundle/source reload')
