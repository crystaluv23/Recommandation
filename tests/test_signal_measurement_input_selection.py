"""Callable-owned input selection; real GPRE reads and synthetic-only arithmetic."""
from dataclasses import replace
from datetime import datetime, timedelta, timezone
import hashlib
import json
from pathlib import Path
from unittest import TestCase
from unittest.mock import patch

from stock_opportunity_agent.artifacts import canonical_json_hash
from stock_opportunity_agent.data.raw_info import RawInfoDocument, RawInfoStore
from stock_opportunity_agent.data.resolution import (
    AcquisitionResult, DataAcquisitionPolicy, EvidenceResolver, RawInfoRequest, _deduplicate_documents, _matches_source_type,
    _rank_documents, _select_required_source_documents,
)
from stock_opportunity_agent.models import ValidationError
from stock_opportunity_agent import signal_library as library

ROOT = Path(__file__).resolve().parents[1]
STAGE = ROOT/'runs/diagnostics/reviewed_gpre_capture_snapshot_20261021_v1/stage'
AS_OF = datetime(2025,5,30,tzinfo=timezone.utc)
COMPANY = 'cik_0000000001'


def fact(tag, end, value, start=None, unit='USD'):
    return {'tag':tag,'end':end,'start':start,'value':value,'unit':unit}


def document(name, facts, *, filed='2025-05-08', padding=''):
    payload = {'schema_version':'sec-company-facts-document-v1','cik':'0000000001',
        'accession_number':name,'filing_date':filed,'form':'10-Q','facts':facts}
    if padding:
        payload['readable_note'] = padding
    clock = datetime.fromisoformat(filed).replace(tzinfo=timezone.utc)
    return RawInfoDocument.create(document_id=name,company_id=COMPANY,
        source_type='sec_company_facts',published_at=clock,available_at=clock+timedelta(days=1),
        content=json.dumps(payload,sort_keys=True,separators=(',',':')),metadata={'cik':'0000000001'})


def spec(function='financial.cash_reserves', *, query=('cash balance liquidity',), **policy):
    return library.SignalSpec(signal_id='input_control',version=1,category='financial',
        description='Measure the actual callable input basis.',
        execution_type=library.SignalExecutionType.DETERMINISTIC,function=function,
        source_types=('financials',), retrieval_policy=library.SignalRetrievalPolicy(
            query_terms=query,**policy))


def snapshot(specs):
    return library.FrozenSignalRegistry(version=1,registry_hash=canonical_json_hash([s.to_dict() for s in specs]),
                                      specs=tuple(specs),skills={})


def executor(specification, docs, **kwargs):
    return library.SignalExecutor(snapshot((specification,)),RawInfoStore(documents=docs),**kwargs)


def noise(count=12, *, tag='OtherConcept', term='cash balance liquidity revenue sales weighted average shares', filed='2024-02-01'):
    return [document('noise-'+str(i),[fact(tag,'2023-12-31',i+1)],filed=filed,padding=(term+' ')*100)
            for i in range(count)]


def eligible(documents, request, cutoff=AS_OF):
    values = [d for d in documents if d.available_at<=cutoff and _matches_source_type(d,request.source_types)
              and (request.lookback_days is None or d.published_at>=cutoff-timedelta(days=request.lookback_days))]
    values,_ = _deduplicate_documents(values)
    return tuple(_rank_documents(values,request))


class SignalMeasurementInputSelectionTests(TestCase):
    def setUp(self):
        for name in ('socket.socket','socket.create_connection'):
            tripwire = patch(name,side_effect=AssertionError('network forbidden in offline selection tests'))
            tripwire.start();self.addCleanup(tripwire.stop)

    def prepare(self, specification, docs, **kwargs):
        ex = executor(specification,docs,**kwargs)
        return ex,ex.prepare_inputs((specification.ref,),company_id=COMPANY,as_of=AS_OF)[0]

    def test_actual_gpre_two_exact_groups_preserve_full_pool_basis_within_ten(self):
        review_path = STAGE/'source-review.json'
        self.assertEqual(hashlib.sha256(review_path.read_bytes()).hexdigest(),
                         'ba2ce1bd99f5fb15c8e8bd51dd634016dfbbbe15c89898c1f81219c6f1919d57')
        review = json.loads(review_path.read_bytes())
        docs = tuple(RawInfoDocument.from_dict(json.loads(Path(r['original_record']['path']).read_bytes()))
            for r in review['records'] if r['verdict']=='admitted' and r['company_id']=='cik_0001309402')
        plan = json.loads((STAGE/'plan.json').read_bytes())
        current = 'rawcap:v1:64c9e4f193885e37ae497a75841bec6dec372f9fddf1ef7649710c28c40fc902'
        for group in plan['groups']:
            specs = []
            for ref in group['refs']:
                signal,v=ref.rsplit(':v',1)
                path=next(Path(group['root']).glob('*/'+signal+'/versions/v'+v+'/spec.json'))
                specs.append(library.SignalSpec.from_dict(json.loads(path.read_bytes())))
            frozen = snapshot(specs)
            ex = library.SignalExecutor(frozen,RawInfoStore(documents=docs))
            # No real Signal is applied; this is actual prepare_inputs and pure helpers only.
            resolutions = ex.prepare_inputs(tuple(group['refs']),company_id='cik_0001309402',as_of=AS_OF,
                                             identity={'cik':'0001309402','ticker':'GPRE'})
            self.assertEqual(len(resolutions),18)
            old_rows={x['signal_ref']:x['resolution'] for x in json.loads((STAGE/(group['name']+'.json')).read_bytes())['resolutions']}
            deterministic_financial=0;financial_q1=0
            for s,r in zip(specs,resolutions,strict=True):
                function=ex.deterministic_functions.get(str(s.function));helper=getattr(function,'__signal_input_facts__',None)
                pool=eligible(docs,r.request)
                selected=tuple(next(d for d in docs if d.document_id==ref.document_id) for ref in r.documents)
                self.assertLessEqual(len(selected),10)
                if 'financials' in r.request.source_types:
                    financial_q1 += current in {d.document_id for d in selected}
                if helper is None:
                    self.assertEqual([d.document_id for d in selected],
                                     [d['document_id'] for d in old_rows[s.ref]['documents']])
                if helper is not None and selected:
                    deterministic_financial += 1
                    self.assertIn(current,{d.document_id for d in selected})
                    self.assertEqual(library._input_basis_identity(helper(s,pool,AS_OF)),
                                     library._input_basis_identity(helper(s,selected,AS_OF)))
                if s.signal_id=='cash_reserves':
                    self.assertEqual(len(pool),59)
                    self.assertIn(current,{d.document_id for d in selected})
                    self.assertEqual(helper(s,selected,AS_OF).facts[0].end,'2025-03-31')
                if s.signal_id=='cash_to_current_liabilities_ratio':
                    self.assertEqual(len(pool),57)
            self.assertEqual(deterministic_financial,6 if group['name']=='default_v6' else 9)
            self.assertEqual(financial_q1,8 if group['name']=='default_v6' else 9)

    def test_long_old_repetition_no_longer_displaces_current_readable_cash(self):
        current=document('current',[fact('CashAndCashEquivalentsAtCarryingValue','2025-03-31',40)])
        old=noise(tag='CashAndCashEquivalentsAtCarryingValue')
        s=spec(minimum_distinct_periods=1)
        ex,r=self.prepare(s,(*old,current))
        pool=eligible((*old,current),r.request)
        self.assertNotIn('current',{d.document_id for d in _select_required_source_documents(list(pool),r.request)})
        self.assertIn('current',{d.document_id for d in r.documents})
        result=ex.execute_batch((s.ref,),company_id=COMPANY,as_of=AS_OF).results[0]
        self.assertEqual(result.measurement.period_end,'2025-03-31')
        self.assertEqual(result.measurement.value,40)

    def test_latest_unmatched_cashflow_cannot_be_hidden_to_resurrect_old_pair(self):
        old=document('old-pair',[
            fact('NetCashProvidedByUsedInOperatingActivities','2024-03-31',-10,'2024-01-01'),
            fact('CashAndCashEquivalentsAtCarryingValue','2024-03-31',30)],filed='2024-05-08')
        latest=document('latest-unmatched',[
            fact('NetCashProvidedByUsedInOperatingActivities','2025-03-31',-10,'2025-01-01',unit='EUR')])
        s=spec('financial.cash_burn_rate_elevated')
        ex,r=self.prepare(s,(*noise(),old,latest))
        self.assertIn('latest-unmatched',{d.document_id for d in r.documents})
        result=ex.execute_batch((s.ref,),company_id=COMPANY,as_of=AS_OF).results[0]
        self.assertEqual(result.value,library.SignalValue.UNAVAILABLE)
        self.assertIn('same-currency',result.interpretation)

    def test_comparison_source_and_exact_share_unit_preserved(self):
        current=document('current',[fact('WeightedAverageNumberOfSharesOutstandingBasic','2025-03-31',110,'2025-01-01',unit='shares')])
        prior=document('prior',[fact('WeightedAverageNumberOfSharesOutstandingBasic','2024-03-31',100,'2024-01-01',unit='shares')],filed='2024-05-08')
        s=spec('financial.net_share_retirement_yoy',query=('weighted average shares',),
               minimum_distinct_periods=2,minimum_period_span_days=330)
        ex,r=self.prepare(s,(*noise(),current,prior))
        self.assertTrue({'current','prior'}<={d.document_id for d in r.documents})
        result=ex.execute_batch((s.ref,),company_id=COMPANY,as_of=AS_OF).results[0]
        self.assertAlmostEqual(result.measurement.value,-0.1)
        for replacement in (None,document('prior',[
                fact('WeightedAverageNumberOfSharesOutstandingBasic','2024-03-31',100,'2024-01-01',unit='USD')],filed='2024-05-08')):
            sources=(*noise(),current,*(() if replacement is None else (replacement,)))
            result=executor(s,sources).execute_batch((s.ref,),company_id=COMPANY,as_of=AS_OF).results[0]
            self.assertEqual(result.value,library.SignalValue.UNAVAILABLE)

    def test_zero_denominator_and_stale_current_keep_failure_basis(self):
        revenue='Revenues'
        current=document('current',[fact(revenue,'2025-03-31',100,'2025-01-01')])
        zero=document('zero',[fact(revenue,'2024-03-31',0,'2024-01-01')],filed='2024-05-08')
        s=spec('financial.revenue_growth_yoy',query=('revenue sales',))
        result=executor(s,(*noise(),current,zero)).execute_batch((s.ref,),company_id=COMPANY,as_of=AS_OF).results[0]
        self.assertEqual(result.value,library.SignalValue.UNAVAILABLE)
        stale=document('stale',[fact('CashAndCashEquivalentsAtCarryingValue','2020-12-31',100)],filed='2021-02-01')
        result=executor(spec(),(*noise(),stale)).execute_batch((spec().ref,),company_id=COMPANY,as_of=AS_OF).results[0]
        self.assertEqual(result.value,library.SignalValue.UNAVAILABLE)
        self.assertIn('stale',result.interpretation)

    def dominance_sources(self, *, witness_required=False):
        a=[fact('Revenues','2025-03-31',100,'2025-01-01'),fact('Revenues','2024-03-31',80,'2024-01-01')]
        b=[fact('RevenueFromContractWithCustomerExcludingAssessedTax','2025-03-31',110,'2025-01-01'),
           fact('RevenueFromContractWithCustomerExcludingAssessedTax','2024-03-31',100,'2024-01-01')]
        witness=document('z-witness',[
            fact('RevenueFromContractWithCustomerExcludingAssessedTax','2010-12-31',1,'2010-01-01'),
            fact('SalesRevenueNet','2010-12-31',100,'2010-01-01')],filed='2011-02-01')
        a_doc=document('operand-a',a+(b if witness_required else []))
        fillers=noise(9 if witness_required else 8,term='revenue')
        return (a_doc,*(() if witness_required else (document('high-b',b,padding='revenue '*200),)),*fillers,witness)

    def test_harmful_optional_fill_does_not_discard_feasible_minimal_operands(self):
        s=spec('financial.revenue_growth_yoy',query=('revenue',),minimum_distinct_periods=2,minimum_period_span_days=330)
        docs=self.dominance_sources()
        ex,r=self.prepare(s,docs)
        self.assertEqual(len(docs),11);self.assertEqual(r.status,'resolved')
        selected=ex.resolver.load_documents(r,as_of=AS_OF)
        full=library._revenue_growth_input_facts(s,eligible(docs,r.request),AS_OF)
        self.assertEqual(library._input_basis_identity(full),library._input_basis_identity(library._revenue_growth_input_facts(s,selected,AS_OF)))
        self.assertEqual(full.facts[0].tag,'Revenues')

    def test_necessary_nonoperand_dominance_witness_survives_bounded_reduction(self):
        s=spec('financial.revenue_growth_yoy',query=('revenue',),minimum_distinct_periods=2,minimum_period_span_days=330)
        docs=self.dominance_sources(witness_required=True)
        ex,r=self.prepare(s,docs)
        self.assertEqual(r.status,'resolved')
        self.assertIn('z-witness',{d.document_id for d in r.documents})
        self.assertLessEqual(len(r.documents),10)
        result=ex.execute_batch((s.ref,),company_id=COMPANY,as_of=AS_OF).results[0]
        self.assertAlmostEqual(result.measurement.value,0.25)

    def test_actual_override_unknown_callable_and_malformed_declaration_paths(self):
        docs=(*noise(),document('current',[fact('CashAndCashEquivalentsAtCarryingValue','2025-03-31',50)]))
        s=spec()
        def override(*args):
            raise AssertionError('prepare_inputs must not execute the actual Signal')
        _,r=self.prepare(s,docs,deterministic_functions={s.function:override})
        pool=eligible(docs,r.request)
        self.assertEqual([d.document_id for d in r.documents],[d.document_id for d in _select_required_source_documents(list(pool),r.request)])
        unknown=replace(s,function='custom.unregistered')
        _,r=self.prepare(unknown,docs)
        self.assertEqual([d.document_id for d in r.documents],[d.document_id for d in _select_required_source_documents(list(pool),r.request)])
        override.__signal_input_facts__ = False
        with self.assertRaisesRegex(ValidationError,'Local document selection failed'):
            self.prepare(s,docs[:1],deterministic_functions={s.function:override})
        override.__signal_input_facts__ = lambda *_args: None
        with self.assertRaisesRegex(ValidationError,'Local document selection failed'):
            self.prepare(s,docs,deterministic_functions={s.function:override})

    def test_changed_selected_sources_invalidate_fingerprint_unchanged_replay_skips(self):
        old=noise(tag='CashAndCashEquivalentsAtCarryingValue')
        current=document('current',[fact('CashAndCashEquivalentsAtCarryingValue','2025-03-31',40)])
        s=spec();ex=executor(s,(*old,current))
        with patch.dict(ex.deterministic_functions,{s.function:library._cash_reserves_signal}):
            first=ex.execute_batch((s.ref,),company_id=COMPANY,as_of=AS_OF)
            same=ex.execute_batch((s.ref,),company_id=COMPANY,as_of=AS_OF,prior_fingerprints=first.document_fingerprints)
            self.assertEqual(same.skipped_unchanged_refs,(s.ref,))
            self.assertEqual(same.signal_calls,0)
            # Old generic selection fingerprint remains a different legitimate cache identity.
            request=first.resolutions[0].request
            generic=_select_required_source_documents(list(eligible((*old,current),request)),request)
            old_fingerprint=tuple(sorted(d.document_id+':'+d.content_hash for d in generic))
            self.assertNotEqual(old_fingerprint,first.document_fingerprints[s.ref])
            changed=ex.execute_batch((s.ref,),company_id=COMPANY,as_of=AS_OF,prior_fingerprints={s.ref:old_fingerprint})
            self.assertEqual(changed.signal_calls,1)
            self.assertEqual(changed.results[0].measurement.value,40)

    def test_usd_basis_and_same_filing_comparison_preference_are_not_replaced(self):
        usd=document('usd',[
            fact('Revenues','2024-12-31',100,'2024-01-01'),fact('Revenues','2023-12-31',80,'2023-01-01')],filed='2025-02-01')
        eur=document('eur-later',[
            fact('Revenues','2025-03-31',1000,'2025-01-01',unit='EUR'),
            fact('Revenues','2024-03-31',1,'2024-01-01',unit='EUR')])
        s=spec('financial.revenue_growth_yoy',query=('revenue',))
        result=executor(s,(*noise(),usd,eur)).execute_batch((s.ref,),company_id=COMPANY,as_of=AS_OF).results[0]
        self.assertAlmostEqual(result.measurement.value,0.25)
        current=document('same-filing',[
            fact('WeightedAverageNumberOfSharesOutstandingBasic','2025-03-31',110,'2025-01-01',unit='shares'),
            fact('WeightedAverageNumberOfSharesOutstandingBasic','2024-03-31',100,'2024-01-01',unit='shares')])
        previous=document('old-unrestated',[
            fact('WeightedAverageNumberOfSharesOutstandingBasic','2024-03-31',200,'2024-01-01',unit='shares')],filed='2024-05-08')
        shares=spec('financial.net_share_retirement_yoy',query=('shares',))
        result=executor(shares,(*noise(),current,previous)).execute_batch((shares.ref,),company_id=COMPANY,as_of=AS_OF).results[0]
        self.assertAlmostEqual(result.measurement.value,-0.1)
        self.assertEqual({e.document_id for e in result.supporting_evidence},{'same-filing'})

    def test_unrepresentable_basis_uses_original_authorized_acquisition_then_gap(self):
        from tests.test_data_resolution import FakeAdapter
        docs=noise(11)
        def needs_all(_spec,documents,as_of):
            return library._SecInputBasis(library._sec_facts(documents,as_of))
        @library.signal_input_facts(needs_all)
        def actual(*_args):
            raise AssertionError('unresolved input must not execute a Signal')
        s=spec();store=RawInfoStore(documents=docs);adapter=FakeAdapter(AcquisitionResult())
        adapter.provider='offline';adapter.source_types=('financials',);adapter.capabilities=('financial_statements',)
        resolver=EvidenceResolver(store,adapters=(adapter,),policy=DataAcquisitionPolicy(
            enabled=True,allowed_providers=('offline',),allowed_source_types=('financials',),
            allowed_capabilities=('financial_statements',),max_requests_per_cycle=1,max_requests_per_run=1))
        ex=library.SignalExecutor(snapshot((s,)),store,resolver=resolver,deterministic_functions={s.function:actual})
        r=ex.prepare_inputs((s.ref,),company_id=COMPANY,as_of=AS_OF)[0]
        self.assertEqual(adapter.calls,1)
        self.assertEqual(r.status,'unresolved')
        self.assertFalse(r.documents)
        self.assertIsNotNone(r.gap)
