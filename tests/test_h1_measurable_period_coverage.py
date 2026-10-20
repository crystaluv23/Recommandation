"""Value-free H1 coverage at the native manifest boundary; no research run."""
import json
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest import TestCase

from stock_opportunity_agent.data.raw_info import RawInfoDocument, RawInfoStore
from stock_opportunity_agent.research.signal_evolution import SignalEvolutionEngine

TAG = 'NetCashProvidedByUsedInOperatingActivities'
CUTOFF = datetime(2024, 8, 1, tzinfo=timezone.utc)


def row(value, start='2024-01-01', end='2024-06-30', *, unit='USD', taxonomy='us-gaap'):
    return {'taxonomy': taxonomy, 'tag': TAG, 'unit': unit, 'value': value,
            'start': start, 'end': end}


def pair():
    return [row(120), row(100, '2023-01-01', '2023-06-30')]


def document(name, company, rows, *, typed=True):
    if typed:
        body = {'schema_version':'sec-company-facts-document-v1',
                'filing_date':'2024-08-01', 'facts': rows}
    else:
        facts = {}
        for item in rows:
            units = facts.setdefault(item['taxonomy'], {}).setdefault(item['tag'], {'units':{}})['units']
            units.setdefault(item['unit'], []).append({
                **{k: v for k, v in item.items() if k not in ('taxonomy','tag','unit','value')},
                'val': item['value'], 'filed':'2024-08-01'})
        body = {'cik':1, 'facts':facts}
    return RawInfoDocument.create(document_id=name, company_id=company,
        source_type='sec_company_facts', published_at=CUTOFF, available_at=CUTOFF,
        content=json.dumps(body, sort_keys=True, separators=(',', ':')))


def manifest(row_groups, *, typed=True, extra_cases=0):
    """Only the actual method's company/cutoff fields are adapted, not an Engine."""
    scopes = [('case-'+str(i), SimpleNamespace(company_id='issuer-'+str(i), prediction_time=CUTOFF))
              for i in range(2 + extra_cases)]
    docs = tuple(document('doc-'+str(i)+'-'+str(j), scope.company_id, rows, typed=typed)
                 for i, (_, scope) in enumerate(scopes[:2]) for j, rows in enumerate(row_groups))
    owner = SimpleNamespace(raw_info_store=RawInfoStore(documents=docs))
    return SignalEvolutionEngine._h1_measurable_evidence_manifest(owner, scopes)


class H1MeasurablePeriodCoverageTests(TestCase):
    def test_same_end_conflicts_are_not_a_comparable_pair(self):
        for typed in (True, False):
            with self.subTest(typed=typed):
                result = manifest([[row(120), row(121)]], typed=typed)
                self.assertEqual(result['structured_financial_concepts'][0]['cases_with_comparable_records'], 0)

    def test_same_end_different_durations_without_prior_do_not_count(self):
        result = manifest([[row(120), row(60,'2024-04-01')]])
        self.assertEqual(result['structured_financial_concepts'][0]['cases_with_comparable_records'], 0)

    def test_normal_typed_and_legacy_pairs_keep_value_free_counts(self):
        for typed in (True, False):
            with self.subTest(typed=typed):
                result = manifest([pair()], typed=typed, extra_cases=1)
                self.assertEqual(result['cohort_case_count'], 3)
                self.assertEqual(result['structured_financial_concepts'], [{
                    'taxonomy':'us-gaap', 'concept':TAG, 'source_display_name':'',
                    'unit':'USD', 'case_count':2, 'cases_with_comparable_records':2}])
                encoded=json.dumps(result)
                self.assertNotIn('issuer-',encoded)
                self.assertNotIn('exact_span',encoded)
                self.assertNotIn('"value"',encoded)

    def test_valid_duration_counts_even_when_other_current_duration_conflicts(self):
        rows = pair() + [row(121), row(60,'2024-04-01'), row(50,'2023-04-01','2023-06-30')]
        result = manifest([rows])
        self.assertEqual(result['structured_financial_concepts'][0]['cases_with_comparable_records'], 2)

    def test_nearest_prior_conflict_does_not_fall_back_to_older_prior(self):
        rows = pair() + [row(101,'2023-01-01','2023-06-30'), row(90,'2022-01-01','2022-06-30')]
        result = manifest([rows])
        self.assertEqual(result['structured_financial_concepts'][0]['cases_with_comparable_records'], 0)

    def test_documents_and_namespaces_are_never_stitched(self):
        for typed in (True, False):
            with self.subTest(typed=typed):
                result = manifest([[pair()[0]], [pair()[1]]], typed=typed)
                self.assertEqual(result['structured_financial_concepts'][0]['cases_with_comparable_records'],0)
                namespace_rows = [pair()[0], {**pair()[1], 'taxonomy':'custom'}]
                result = manifest([namespace_rows],typed=typed)
                self.assertEqual([c['cases_with_comparable_records'] for c in result['structured_financial_concepts']],[0,0])

    def test_currencies_count_independently_without_default_currency(self):
        rows = pair() + [{**r,'unit':'EUR'} for r in pair()]
        result = manifest([rows])
        self.assertEqual({c['unit']:c['cases_with_comparable_records'] for c in result['structured_financial_concepts']}, {'USD':2,'EUR':2})

    def test_equivalent_dates_and_values_do_not_create_false_conflict(self):
        rows = pair()+[row('120.00', '20240101', '20240630')]
        result=manifest([rows])
        self.assertEqual(result['structured_financial_concepts'][0]['cases_with_comparable_records'],2)


    def test_nullable_start_instant_rows_agree_with_native_fact_pair(self):
        from stock_opportunity_agent.research.mining_agent_tools import (
            build_same_concept_relations, project_facts_from_documents)
        rows=[row(120,None,'2024-06-30'),row(100,None,'2023-06-30')]
        doc=document('nullable-start','issuer',rows)
        projected=project_facts_from_documents((doc,),case_ref='case')
        self.assertEqual(len(build_same_concept_relations(projected)),1)
        self.assertEqual(manifest([rows])['structured_financial_concepts'][0]['cases_with_comparable_records'],2)

    def test_actual_h1_outgoing_request_explains_existential_partial_coverage(self):
        from stock_opportunity_agent.research.evolution_signal_roles import LLMSignalMiningModel
        class RequestCaptured(BaseException):
            pass
        captured=[]
        class Caller:
            def complete_json(self, **kwargs):
                captured.append(kwargs)
                raise RequestCaptured()
        payload={'measurable_evidence_manifest':manifest([[row(120),row(121)]]),
                 'limits':{'hypothesis_limit':1},'hypothesis_slots':['proposal-001']}
        with self.assertRaises(RequestCaptured):
            LLMSignalMiningModel(Caller()).propose_hypotheses(payload)
        self.assertEqual(len(captured),1)
        system=captured[0]['system_prompt']
        self.assertIn('at least one valid local pair',system)
        self.assertIn('does not guarantee a unique measurement',system)
        self.assertIn('absent manifest families do not prove source absence',system)
        self.assertEqual(captured[0]['payload']['measurable_evidence_manifest'],payload['measurable_evidence_manifest'])
        self.assertNotIn('already expose latest-plus-comparable',system)
