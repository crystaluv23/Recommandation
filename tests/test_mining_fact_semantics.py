"""Local source-format/period regressions; no completed diagnostic is reentered."""
from dataclasses import replace
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
from unittest import TestCase

from stock_opportunity_agent.data.raw_info import RawInfoDocument, RawInfoStore
from stock_opportunity_agent.research.evolution_core import _company_facts_context
from stock_opportunity_agent.research.mining_agent_tools import (
    project_facts_from_documents, build_same_concept_relations, compute_statistic,
    _unique_latest_fact, _unique_period_pair,
)
from stock_opportunity_agent.research.mining_closure import execute_measurement
from stock_opportunity_agent.research.mining_controller import LabelAwareMiningController
from stock_opportunity_agent.research.mining_replay import measure_arrival
from tests.scheme_evolution_test_support import make_case

TAG = 'NetCashProvidedByUsedInOperatingActivities'
NOW = datetime(2024, 8, 1, tzinfo=timezone.utc)


def document(name, rows, *, typed=True):
    if typed:
        payload = {'schema_version': 'sec-company-facts-document-v1', 'filing_date': '2024-08-01', 'facts': rows}
    else:
        units = {}
        for row in rows:
            units.setdefault(row.get('unit', 'USD'), []).append({k: v for k, v in row.items() if k not in ('unit', 'taxonomy', 'tag')})
        payload = {'cik': 1, 'facts': {'us-gaap': {TAG: {'units': units}}}}
    return RawInfoDocument.create(document_id=name, company_id='probe-issuer', source_type='sec_company_facts',
        published_at=NOW, available_at=NOW, metadata={'cik': '0000000001'},
        content=json.dumps(payload, sort_keys=True, separators=(',', ':')))


def typed_row(value, start, end, unit='USD'):
    return {'taxonomy': 'us-gaap', 'tag': TAG, 'unit': unit, 'value': value, 'start': start, 'end': end}


def pair_rows(current=120, prior=100):
    return [typed_row(current, '2024-01-01', '2024-06-30'), typed_row(prior, '2023-01-01', '2023-06-30')]


def ambiguity_rows():
    return pair_rows() + [typed_row(121, '2024-01-01', '2024-06-30'),
        typed_row(60, '2024-04-01', '2024-06-30'), typed_row(50, '2023-04-01', '2023-06-30'),
        typed_row(900, '2024-01-01', '2024-06-30', 'EUR'), typed_row(800, '2023-01-01', '2023-06-30', 'EUR')]


def facts(doc):
    return project_facts_from_documents((doc,), case_ref='case-001')


class MiningFactSemanticsTests(TestCase):
    def test_exact_original0671_context_records_reach_native_facts(self):
        root = Path(__file__).resolve().parents[1]
        path = root / 'runs/diagnostics/reviewed_gpre_capture_snapshot_20261021_v1/stage/snapshot/documents/0671.json'
        raw = path.read_bytes()
        self.assertEqual(hashlib.sha256(raw).hexdigest(), 'ab081c728d390ce68c10d59336be1e8196ab1c4bb33c0febac2fdfb680347c31')
        doc = RawInfoDocument.from_dict(json.loads(raw))
        context = _company_facts_context(doc, max_content_chars=12000, query=None)
        records = [r for group in context['concepts'] for r in group['records']]
        self.assertEqual(len(records), 19)
        projected = facts(doc)
        self.assertEqual(len(projected), len(records))
        self.assertTrue(all(f.exact_span in doc.content and 'value' in json.loads(f.exact_span) for f in projected))
        self.assertEqual(path.read_bytes(), raw)

    def test_schema_specific_value_never_falls_back_to_other_key(self):
        rows = pair_rows()
        rows[0]['val'] = 999
        projected = facts(document('typed', rows))
        self.assertEqual({f.value for f in projected}, {'120', '100'})
        legacy = [{'start':'2024-01-01','end':'2024-06-30','filed':'2024-08-01','val':120,'value':999},
                  {'start':'2023-01-01','end':'2023-06-30','filed':'2024-08-01','val':100,'value':998}]
        self.assertEqual({f.value for f in facts(document('legacy', legacy, typed=False))}, {'120', '100'})
        missing = [{k:v for k,v in row.items() if k != 'value'} for row in rows]
        self.assertEqual(facts(document('missing-value', missing)), ())

    def test_simple_legacy_pair_keeps_normal_source_periods_and_literal(self):
        rows = [{'start':'2024-01-01','end':'2024-06-30','filed':'2024-08-01','val':120},
                {'start':'2023-01-01','end':'2023-06-30','filed':'2024-08-01','val':100}]
        doc = document('legacy', rows, typed=False)
        projected = facts(doc)
        self.assertEqual(len(projected), 2)
        pair = _unique_period_pair(projected)
        self.assertEqual([f.value for f in pair], ['120', '100'])
        self.assertTrue(all(f.exact_span in doc.content for f in projected))
        self.assertEqual(compute_statistic('latest_over_comparable_prior', [f.fact_ref for f in pair], facts=projected).value, '1.200000')

    def test_legacy_latest_alternatives_are_not_deduplicated_by_end(self):
        rows = [{**r, 'val': r['value'], 'filed':'2024-08-01'} for r in ambiguity_rows()]
        doc = document('legacy-alternatives', rows, typed=False)
        projected = facts(doc)
        self.assertEqual(len(projected), 7)
        self.assertEqual(sum(f.record_selection == 'latest' for f in projected), 4)
        context = _company_facts_context(doc, max_content_chars=200, query=None)
        self.assertEqual(context['concepts'], [])
        self.assertTrue(context['partial'])

    def test_valid_local_quarter_and_eur_pairs_survive_halfyear_conflict(self):
        projected = facts(document('alternatives', ambiguity_rows()))
        self.assertEqual(sum(f.record_selection == 'latest' for f in projected), 4)
        by_ref = {f.fact_ref:f for f in projected}
        relations = build_same_concept_relations(projected)
        self.assertEqual({tuple(by_ref[ref].value for ref in relation.fact_refs) for relation in relations}, {('60','50'),('900','800')})
        self.assertIsNone(_unique_latest_fact(projected))
        self.assertIsNone(_unique_period_pair(projected))

    def test_no_implicit_cross_document_pair_but_explicit_compute_remains_legal(self):
        a = facts(document('a', [pair_rows()[0]]))
        b = facts(document('b', [pair_rows()[1]]))
        self.assertEqual(build_same_concept_relations((*a,*b)), ())
        self.assertIsNone(_unique_period_pair((*a,*b)))
        self.assertEqual(compute_statistic('latest_over_comparable_prior', [a[0].fact_ref,b[0].fact_ref], facts=(*a,*b)).value, '1.200000')

    def test_equal_numeric_spelling_duplicates_are_not_conflicts_or_new_observations(self):
        a = facts(document('a', pair_rows()))
        b = facts(document('b', pair_rows('120.0','100.00')))
        for collection in ((*a,*b),(*b,*a),(*a,*a)):
            self.assertIsNotNone(_unique_latest_fact(collection))
            self.assertIsNotNone(_unique_period_pair(collection))
        conflict = facts(document('conflict', pair_rows(121,100)))
        self.assertIsNone(_unique_latest_fact((*a,*conflict)))

    def test_prior_nearest_comparable_and_conflict_do_not_fall_back_to_older(self):
        rows = pair_rows() + [typed_row(90, '2022-01-01', '2022-06-30')]
        doc = document('prior', rows)
        pair = _unique_period_pair(facts(doc))
        self.assertEqual(pair[1].value, '100')
        rows.append(typed_row(101, '2023-01-01', '2023-06-30'))
        self.assertIsNone(_unique_period_pair(facts(document('prior-conflict', rows))))

    def test_summary_closure_and_replay_preserve_ambiguous_source_denominator(self):
        doc = document('ambiguous', ambiguity_rows())
        store = RawInfoStore(documents=(doc,)); case = make_case('probe-issuer',4.0)
        tool = LabelAwareMiningController(store=store, model=None, case_pairs=(('case-001',case),),
            measurable_evidence_manifest={}, signal_catalog=(), seed='hypothesis')
        tool._facts = {f.fact_ref:f for f in facts(doc)}
        summary = tool._group_summary((TAG,))['positive']['concepts'][TAG]
        self.assertEqual(summary['available_cases'], ['case-001'])
        self.assertEqual(summary['latest'], {})
        self.assertEqual(summary['comparable_prior'], {})
        self.assertIn('case-001', summary['unresolved_basis_cases'])
        for execution in ({'kind':'concept_latest_at_least','concept':TAG,'threshold':1},
            {'kind':'concept_ratio_at_least','concept':TAG,'threshold':1},
            {'kind':'cross_document_concepts','concepts':[TAG],'thresholds':[1]}):
            self.assertFalse(execute_measurement(execution,store,case)['available'])
        replay = measure_arrival(store,(case,),({'proposal_ref':'fixture','measurement':{'observable':TAG},'retrieval_intent':{}},))
        self.assertEqual(replay['cohort_case_count'],1)
        self.assertEqual(replay['concept_catalog_size'],1)
        concept = replay['hypotheses'][0]['concept_inputs'][0]
        self.assertEqual(concept['cases_with_latest'],0)
        self.assertEqual(concept['cases_with_comparable_pair'],0)

    def test_native_refetch_invalidates_current_auto_pair_but_not_ledger_or_explicit_compute(self):
        doc = document('changing-knowledge', ambiguity_rows())
        store=RawInfoStore(documents=(doc,));case=make_case('probe-issuer',4.0)
        tool=LabelAwareMiningController(store=store,model=None,case_pairs=(('case-001',case),),
            measurable_evidence_manifest={},signal_catalog=(),seed='hypothesis')
        all_facts=facts(doc)
        partial=[f for f in all_facts if f.unit=='USD' and f.value in {'120','100'}]
        tool._facts={f.fact_ref:f for f in partial}
        old_pair=build_same_concept_relations(partial)[0]
        tool._relations[old_pair.relation_ref]=old_pair
        explicit=compute_statistic('latest_over_comparable_prior',old_pair.fact_refs,facts=partial)
        tool._relations[explicit.relation_ref]=explicit
        tool._append('fixture_prior_read',{},payload={'relation_ref':old_pair.relation_ref})
        history=tool.ledger.entries
        raw={'action':'fetch_evidence','case_refs':['case-001'],'source_families':['financial'],
            'max_documents':1,'rationale':['Read the whole synthetic source.']}
        tool._validate_action_shape(raw);tool._execute('fetch_evidence',raw)
        self.assertNotIn(old_pair.relation_ref,tool._relations)
        self.assertIn(explicit.relation_ref,tool._relations)
        self.assertEqual(tool.ledger.entries[:len(history)],history)
        size=len(tool._facts)
        tool._execute('fetch_evidence',raw)
        self.assertEqual(len(tool._facts),size)

    def test_typed_namespaces_separate_when_proved_in_exact_span(self):
        rows=pair_rows()+[{**r,'taxonomy':'custom'} for r in pair_rows(900,800)]
        projected=facts(document('namespaces',rows))
        self.assertEqual(len(build_same_concept_relations(projected)),2)
        self.assertIsNone(_unique_latest_fact(projected))

    def test_basic_and_extended_iso_dates_compare_by_calendar_without_rewriting_literals(self):
        for typed in (True, False):
            rows = [{'taxonomy':'us-gaap','tag':TAG,'unit':'USD','end':'2024-06-30','value':120,'val':120},
                    {'taxonomy':'us-gaap','tag':TAG,'unit':'USD','end':'20240101','value':100,'val':100}]
            projected=facts(document('calendar-'+str(typed),rows,typed=typed))
            by_value={f.value:f for f in projected}
            self.assertEqual(by_value['120'].record_selection,'latest')
            self.assertEqual(by_value['100'].record_selection,'comparable_prior')
            self.assertEqual(by_value['100'].period['end'],'20240101')
            self.assertEqual([f.value for f in _unique_period_pair(projected)],['120','100'])
            duplicate=replace(by_value['120'],fact_ref='equivalent-calendar',period={'end':'20240630'})
            self.assertIsNotNone(_unique_latest_fact((*projected,duplicate)))

    def test_legacy_reported_rows_use_utc_day_and_disclose_invalid_or_future_dates(self):
        rows=[{'end':'2024-07-31','filed':'2024-07-31','val':120},
              {'end':'2024-08-01','filed':'2024-07-31','val':999},
              {'end':'2024-07-30','filed':'bad','val':998},
              {'start':'bad','end':'2024-07-31','val':997},
              {'start':'2024-08-01','end':'2024-07-31','val':996},
              {'end':'bad','val':995},
              {'end':'2024-07-30','filed':'2024-08-01','val':994}]
        doc=document('legacy-pit',rows,typed=False)
        # Local Aug 1 is still July 31 UTC: reported Aug 1 rows remain future.
        doc=replace(doc,published_at=datetime.fromisoformat('2024-08-01T00:30:00+02:00'),
                    available_at=datetime.fromisoformat('2024-08-01T00:30:00+02:00'))
        context=_company_facts_context(doc,max_content_chars=12000,query=None)
        self.assertTrue(context['partial'])
        self.assertEqual([f.value for f in facts(doc)],['120'])
        self.assertTrue(all(f.exact_span in doc.content for f in facts(doc)))

    def test_closure_nonfinite_or_overflow_is_unknown_but_finite_zero_remains_known(self):
        case=make_case('probe-issuer',4.0)
        for current,prior in (('NaN',100),('inf',100),('-inf',100),(120,'NaN'),(120,'inf'),('1e308','1e-308')):
            store=RawInfoStore(documents=(document('nonfinite',pair_rows(current,prior)),))
            result=execute_measurement({'kind':'concept_ratio_at_least','concept':TAG,'threshold':1},store,case)
            self.assertFalse(result['available'])
        for value in ('NaN','inf','-inf'):
            store=RawInfoStore(documents=(document('nonfinite-latest',pair_rows(value,100)),))
            for execution in ({'kind':'concept_latest_at_least','concept':TAG,'threshold':1},
                {'kind':'cross_document_concepts','concepts':[TAG],'thresholds':[1]}):
                self.assertFalse(execute_measurement(execution,store,case)['available'])
        store=RawInfoStore(documents=(document('zero',pair_rows(0,100)),))
        result=execute_measurement({'kind':'concept_latest_at_least','concept':TAG,'threshold':1},store,case)
        self.assertTrue(result['available']);self.assertFalse(result['positive_evidence']);self.assertEqual(result['value'],0)
