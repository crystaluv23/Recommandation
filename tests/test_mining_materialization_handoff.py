"""Whole, seed-local source evidence reaches the actual S5 request boundary."""
from datetime import timedelta
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import types
from unittest import TestCase

from stock_opportunity_agent.data.raw_info import RawInfoDocument, RawInfoStore
from stock_opportunity_agent.llm import get_model
from stock_opportunity_agent.models import ValidationError
from stock_opportunity_agent.research.evolution_transport import StructuredRoleClient, ExternalAttemptLedger
from stock_opportunity_agent.research.mining_role_model import MiningRequestBudgetExhausted
from stock_opportunity_agent.research.signal_evolution import SignalEvolutionEngine
from tests.test_mining_controller import _controller, _fixture_store
from tests.scheme_evolution_test_support import (
    make_case, EmptyMiningModel, NoChangeUpdateModel, SignalRegistry,
    SEED_CATALOG, PlanMetaMemory, EvolutionWorkspace,
)


def execute(controller, action, **kwargs):
    raw = dict(action=action, rationale=['Explicit offline source-handoff fixture.'], **kwargs)
    controller._validate_action_shape(raw)
    controller._execute(action, raw)


def engine():
    result = object.__new__(SignalEvolutionEngine)
    result.slow_role_identity_guards = ('IssuerPrivate',)
    result.validator = SimpleNamespace(forbidden_identity_terms=())
    return result


class MiningMaterializationHandoffTests(TestCase):
    def test_actual_long_fact_and_thirteenth_unit_are_whole_and_source_typed(self):
        path = Path(__file__).resolve().parents[1]/'runs/diagnostics/reviewed_gpre_capture_snapshot_20261021_v1/stage/snapshot/documents/1179.json'
        original = path.read_bytes(); document = RawInfoDocument.from_dict(json.loads(original))
        cases, _ = _fixture_store()
        case = SimpleNamespace(case_id='opaque-source-test', company_id=document.company_id,
            prediction_time=document.available_at + timedelta(days=1), ground_truth=cases[0].ground_truth)
        controller = _controller(RawInfoStore(documents=(document,)), [case], object(), seed='discovery')
        execute(controller, 'fetch_evidence', case_refs=['case-001'], source_families=['financial'], max_documents=1)
        fact = next(f for f in controller._facts.values() if len(f.exact_span)>600)
        refs = list(controller._facts)[:13]
        if fact.fact_ref not in refs:
            refs[0] = fact.fact_ref
        rows = SignalEvolutionEngine._controller_evidence_excerpts(
            {'evidence_refs': refs}, controller.materialization_evidence())
        self.assertEqual(len(rows), 13)
        row = next(r for r in rows if r['ref']==fact.fact_ref)
        self.assertEqual(row['exact_span'], fact.exact_span)
        self.assertEqual(json.loads(row['exact_span'])['taxonomy'], fact.taxonomy)
        self.assertEqual(row['document_source_type'], 'sec_company_facts')
        self.assertEqual(row['content_hash'], document.content_hash)
        self.assertEqual(path.read_bytes(), original)

    def test_late_reads_keep_target_scope_and_never_export_unread_body_or_metadata(self):
        cases, _ = _fixture_store(); case = cases[0]
        document = RawInfoDocument.create(document_id='fixture-late-read', company_id=case.company_id,
            source_type='sec_filing', published_at=case.prediction_time, available_at=case.prediction_time,
            content='<html><script>HIDDEN_BODY</script><p>'+'intro '*700+'</p><p>ACTUAL_TAIL</p></html>',
            metadata={'private_unread': 'UNREAD_METADATA'})
        controller = _controller(RawInfoStore(documents=(document,)), [case], object(), seed='discovery')
        execute(controller,'fetch_evidence',case_refs=['case-001'],source_families=['filing'],max_documents=1)
        docref = 'document-'+document.document_id
        self.assertNotIn(docref, controller.materialization_evidence())
        event = next(iter(controller._events.values()))
        self.assertNotIn(event.event_ref, controller.materialization_evidence())
        offset = document.content.index('ACTUAL_TAIL')
        execute(controller,'read_span',document_ref=docref,offset=offset,length=100)
        execute(controller,'read_span',event_ref=event.event_ref,offset=offset,length=100)
        evidence = controller.materialization_evidence()
        reads = evidence[docref]['read_windows']
        self.assertEqual({r['target'] for r in reads},{'document_ref','event_ref'})
        self.assertEqual({r['ref'] for r in reads},{docref,event.event_ref})
        self.assertEqual(len(reads),2)
        self.assertTrue(all(r['raw_window_chars']<r['length'] for r in reads))
        serialized = json.dumps(evidence[docref])
        self.assertIn('ACTUAL_TAIL',serialized)
        for forbidden in ('HIDDEN_BODY','UNREAD_METADATA','intro '*700):
            self.assertNotIn(forbidden,serialized)
        self.assertTrue(all(r['readable_text']=='ACTUAL_TAIL' for r in reads))
        self.assertNotIn('exact_span',evidence[event.event_ref])
        self.assertEqual(len(evidence[event.event_ref]['read_windows']),2)

    def test_relation_citation_resolves_whole_operands_and_missing_dependency_fails(self):
        cases, store = _fixture_store()
        controller = _controller(store,cases,object(),seed='discovery')
        execute(controller,'fetch_evidence',case_refs=['case-001'],source_families=['financial'],max_documents=1)
        facts = list(controller._facts.values())[:2]
        execute(controller,'compute_statistic',rule='latest_over_latest',fact_refs=[f.fact_ref for f in facts])
        ref = controller._last_action_result['relation_ref']
        evidence = controller.materialization_evidence()
        rows = SignalEvolutionEngine._controller_evidence_excerpts({'evidence_refs':[ref]},evidence)
        self.assertEqual([r['ref'] for r in rows],[ref,*[f.fact_ref for f in facts]])
        del evidence[facts[0].fact_ref]
        with self.assertRaisesRegex(ValidationError,'source handoff'):
            SignalEvolutionEngine._controller_evidence_excerpts({'evidence_refs':[ref]},evidence)

    def test_explicitly_bounded_native_caller_stops_without_an_inbox_or_module_repair(self):
        class Bounded(StructuredRoleClient):
            def complete_json(self, **kwargs):
                return super().complete_json(**kwargs,max_request_tokens=10)
        with TemporaryDirectory() as directory:
            root = Path(directory)
            caller = Bounded(registration=get_model('independent-subagent'),
                contract=SimpleNamespace(contract_hash='a'*64,limits={'max_local_role_calls':2}),
                workspace=root,ledger=ExternalAttemptLedger(root/'unused.json',max_attempts=1,max_total_cost=1),
                allow_external=False,environ={})
            with self.assertRaises(MiningRequestBudgetExhausted):
                engine()._materialize_module_call('spec','Inspect complete evidence.',
                    {'candidate':{},'candidate_contract':{},'cited_evidence':[]},caller=caller)
            self.assertFalse(list((root/'local_roles/inbox').glob('*.json')))

    def test_actual_engine_keeps_each_candidate_with_its_producing_seed_reads(self):
        body = 'FIRST_WINDOW '+('A'*1000)+' SECOND_WINDOW '+('B'*1000)
        second_offset = body.index('SECOND_WINDOW')
        class Caller:
            def complete_json(self, *, payload, **kwargs):
                last = payload.get('last_action_result') or {}
                raw = {'rationale':['Explicit offline seed-scope fixture.']}
                if not payload['known_event_refs']:
                    raw.update(action='fetch_evidence',case_refs=[payload['case_refs'][0]],
                        source_families=['filing'],max_documents=1)
                elif last.get('action')!='read_span':
                    raw.update(action='read_span',document_ref='document-fixture-seed-source',
                        offset=0 if payload['seed']=='hypothesis' else second_offset,length=40)
                else:
                    raw.update(action='propose_candidate',candidate={
                        'measurement':{'observable':'fixture_seed_scope_quantity','value_kind':'numeric','normalization':'fixture'},
                        'evidence_refs':['document-fixture-seed-source'],
                        'falsifiers':[{'condition':'missing','expected_observation':'unavailable'}]})
                    if payload['seed']=='hypothesis':raw['need_dispositions']=[]
                from stock_opportunity_agent.research.evolution_core import AgentUsage
                return raw,AgentUsage()
        with TemporaryDirectory() as directory:
            root = Path(directory);cases=(make_case('dev_a',1.1),make_case('dev_b',4.0))
            doc=RawInfoDocument.create(document_id='fixture-seed-source',company_id=cases[0].company_id,
                source_type='sec_filing',published_at=cases[0].prediction_time,
                available_at=cases[0].prediction_time,content=body)
            registry=SignalRegistry(root/'signals');registry.install_catalog(SEED_CATALOG)
            mining=EmptyMiningModel();mining.caller=Caller()
            host=SignalEvolutionEngine(registry=registry,raw_info_store=RawInfoStore(documents=(doc,)),
                discovery_cases=cases,meta_memory=PlanMetaMemory(),workspace=EvolutionWorkspace(root/'workspace'),
                mining_model=mining,update_model=NoChangeUpdateModel(),llm_signal_runner=None)
            host._mining_context=types.MethodType(lambda self,**kwargs:{},host)
            seen={}
            def capture(self,candidate,*,seed,evidence,**kwargs):
                rows=self._controller_evidence_excerpts(candidate,evidence)
                seen[seed]=rows[0]['read_windows']
                return None
            host._materialize_controller_candidate=types.MethodType(capture,host)
            host._run_controller_mining_axis(cycle_id=1,axis_id='surge_direction',
                research_axis={'axis_id':'surge_direction'},dev_cases=cases,check_cases=(),
                labels_by_case_id={case.case_id:'positive' if case.ground_truth.is_surge else 'control' for case in cases})
            self.assertEqual(set(seen),{'hypothesis','discovery'})
            self.assertEqual([r['offset'] for r in seen['hypothesis']],[0])
            self.assertEqual([r['offset'] for r in seen['discovery']],[second_offset])
