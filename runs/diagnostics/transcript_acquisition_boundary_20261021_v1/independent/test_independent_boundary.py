"""Synthetic guard consumers and real native raw-client/cache connections only."""
from copy import deepcopy
from datetime import datetime, timezone, timedelta, date
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import socket
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch
sys.dont_write_bytecode = True
REPO=Path('/Users/l/Project/Recommandation')
HERE=Path(__file__).resolve().parent
from stock_opportunity_agent.data import (AlphaVantageClient,FinnhubClient,DataCapability,ManagedHttpTransport,RawDataCache,RequestLedger,SourceBudget,RequestStatus)
from stock_opportunity_agent.data.raw_info import RawInfoStore,RawInfoDocument
from stock_opportunity_agent.data.resolution import (AcquisitionFailure,AcquisitionResult,DataAcquisitionPolicy,DataAcquisitionBudget,DataGapReason,EvidenceResolver,RawInfoRequest)
from stock_opportunity_agent.data.sources.core import UrllibJsonTransport
from stock_opportunity_agent.cases.label_store import LabelStore
from stock_opportunity_agent.research import evolution_control as factory
from stock_opportunity_agent.data import acquisition

def load(path,name):
    s=importlib.util.spec_from_file_location(name,path);m=importlib.util.module_from_spec(s);sys.modules[name]=m;s.loader.exec_module(m);return m
if os.environ.get('TRANSCRIPT_REVIEW_ORIGINAL')=='1':
    # .txt original requires an explicit SourceFileLoader; no shared source replacement.
    from importlib.machinery import SourceFileLoader
    def load_original(path,name):
        s=importlib.util.spec_from_loader(name,SourceFileLoader(name,str(path)));m=importlib.util.module_from_spec(s);sys.modules[name]=m;s.loader.exec_module(m);return m
    original_path=HERE/'original-882f-acquisition.py.txt'
    assert hashlib.sha256(original_path.read_bytes()).hexdigest()=='882f765da65b3352cb638290378b1bebb5d7afaee4f656c9664d10b4a4eaf092'
    assert hashlib.sha256((HERE/'original-run_cold_start_formal.py.txt').read_bytes()).hexdigest()=='4b3aa81b8536a9f73a427691222fdbe5095e00fa8f22eeb9839413dd1d25665f'
    acquisition=load_original(original_path,'independent_original_transcript_acquisition')
    legacy=load_original(HERE/'original-run_cold_start_formal.py.txt','independent_original_transcript_formal')
else:
    legacy=load(REPO/'scripts/run_cold_start_formal.py','independent_candidate_transcript_formal')
Adapter=acquisition.AlphaVantageTranscriptAdapter
NOW=datetime(2025,1,15,12,tzinfo=timezone.utc)
TOKEN='offline-example-token'
EVENTS=[]

def denied(*a,**k):
    EVENTS.append('forbidden');raise AssertionError('Forbidden real network/labels')

def policy(enabled=True):
    return DataAcquisitionPolicy(enabled=enabled,allowed_providers=('*',),allowed_capabilities=('*',),allowed_source_types=('*',),max_requests_per_cycle=4,max_requests_per_run=4) if enabled else DataAcquisitionPolicy()

class Provider:
    transport=None
    def __init__(self):self.calls=[]
    def earnings(self,symbol):
        self.calls.append(('earnings',symbol))
        return {'annualEarnings':[{'fiscalDateEnding':'2024-12-31'}], 'quarterlyEarnings':[
            {'fiscalDateEnding':p,'reportedDate':d} for p,d in [('2024-03-31','2024-04-25'),('2024-06-30','2024-07-25'),('2024-09-30','2024-10-25'),('2024-12-31','2025-01-02')]]}
    def earnings_call_transcript(self,symbol,quarter):
        self.calls.append(('transcript',symbol,quarter));return {'symbol':symbol,'quarter':quarter,'transcript':[{'speaker':'CEO','content':'Only a partial remark, not public-content proof.'}]}

class BottomHTTP:
    """Only the provider HTTP boundary is fake; client/managed/cache stay native."""
    def __init__(self,bodies):self.bodies=bodies;self.calls=[]
    def get_json(self,url,headers):
        from urllib.parse import urlparse,parse_qs
        self.calls.append(url);q=parse_qs(urlparse(url).query)
        key=q.get('function',q.get('id',q.get('symbol')))[0]
        return deepcopy(self.bodies[key])

class BoundaryTests(unittest.TestCase):
    def test_direct_all_aliases_cannot_turn_report_or_ad_hoc_fields_into_proof(self):
        for alias in ('earnings_call','transcript','earnings_transcript'):
            with self.subTest(alias=alias):
                client=Provider();a=Adapter(client)
                with self.assertRaises(AcquisitionFailure) as caught:
                    a.acquire(RawInfoRequest('x','Read call',(alias,)),company_id='synthetic',identity={'ticker':'TEST','public_at':'2024-10-26T00:00:00Z','proof_verified':True},as_of=NOW)
                self.assertEqual(caught.exception.reason,DataGapReason.HISTORICAL_DATA_UNAVAILABLE)
                self.assertEqual(client.calls,[])
        with self.assertRaises(AcquisitionFailure) as caught:
            Adapter(None).acquire(RawInfoRequest('x','Read call',('transcript',)),company_id='synthetic',identity={},as_of=NOW)
        self.assertEqual(caught.exception.reason,DataGapReason.HISTORICAL_DATA_UNAVAILABLE)

    def test_resolver_gap_serialization_memo_and_reservation_are_not_HTTP(self):
        client=Provider();store=RawInfoStore();budget=DataAcquisitionBudget()
        resolver=EvidenceResolver(store,adapters=(Adapter(client),),policy=policy(),budget=budget)
        request=RawInfoRequest('call','Read historical transcript',('earnings_call',))
        self.assertFalse(resolver.can_acquire(request))
        self.assertEqual(resolver.acquisition_unavailability_reason(request),'historical_data_unavailable')
        for _ in range(2):
            result=resolver.resolve(request,company_id='synthetic',identity={'ticker':'TEST'},as_of=NOW)
            self.assertEqual(result.status,'unresolved');self.assertEqual(result.gap.reason,DataGapReason.HISTORICAL_DATA_UNAVAILABLE)
            self.assertEqual(json.loads(json.dumps(result.to_dict()))['data_gap']['reason'],'historical_data_unavailable')
        self.assertEqual(budget.cycle_requests,1);self.assertEqual(budget.run_requests,1)
        self.assertEqual(client.calls,[]);self.assertEqual(store.documents,())
        self.assertTrue(any(e.kind=='acquisition_failure_reused' for e in result.events))

    def test_native_factory_returns_typed_gap_without_touching_provider(self):
        with tempfile.TemporaryDirectory() as tmp,patch.object(factory,'AlphaVantageTranscriptAdapter',Adapter):
            resolver=factory._build_evidence_resolver(Path(tmp),RawInfoStore(),contract=SimpleNamespace(data_acquisition=policy()),allow_data_external=True,environ={'ALPHA_VANTAGE_API_KEY':TOKEN},cycle_id=1)
            result=resolver.resolve(RawInfoRequest('call','Read call',('earnings_transcript',)),company_id='synthetic',identity={'ticker':'TEST'},as_of=NOW)
            self.assertEqual(result.gap.reason,DataGapReason.HISTORICAL_DATA_UNAVAILABLE)
            self.assertFalse(resolver.can_acquire(result.request))
            self.assertEqual(resolver.budget.run_requests,1)
            self.assertFalse((Path(tmp)/'data_requests.jsonl').exists(),'No underlying managed HTTP ledger request')

    def test_local_consumption_and_future_exclusion_do_not_claim_public_proof(self):
        local=RawInfoDocument.create(document_id='synthetic-local',company_id='synthetic',source_type='transcript',published_at=NOW-timedelta(days=2),available_at=NOW-timedelta(days=1),content='Synthetic supplied eligible local content; no source proof claim.')
        future=RawInfoDocument.create(document_id='synthetic-future',company_id='synthetic',source_type='transcript',published_at=NOW,available_at=NOW+timedelta(days=1),content='Future local content')
        client=Provider();resolver=EvidenceResolver(RawInfoStore(documents=(local,future)),adapters=(Adapter(client),),policy=policy())
        result=resolver.resolve(RawInfoRequest('local','Read local',('earnings_call',)),company_id='synthetic',identity={},as_of=NOW)
        self.assertEqual(result.status,'resolved');self.assertEqual([d.document_id for d in result.documents],['synthetic-local'])
        self.assertEqual(client.calls,[]);self.assertEqual(resolver.budget.run_requests,0)
        blocked=EvidenceResolver(RawInfoStore(),adapters=(Adapter(client),),policy=policy(False)).resolve(result.request,company_id='synthetic',identity={'ticker':'TEST'},as_of=NOW)
        self.assertEqual(blocked.gap.reason,DataGapReason.EXTERNAL_NOT_AUTHORIZED)

    def test_generic_other_source_fallback_survives_transcript_unavailability(self):
        local=RawInfoDocument.create(document_id='synthetic-filing',company_id='synthetic',source_type='filing',published_at=NOW,available_at=NOW,content='Synthetic filing alternative')
        class Filing:
            provider='synthetic-filing';source_types=('filing',);capabilities=('filings',)
            def acquire(self,*a,**k):return AcquisitionResult(documents=(local,))
        client=Provider();resolver=EvidenceResolver(RawInfoStore(),adapters=(Adapter(client),Filing()),policy=policy())
        result=resolver.resolve(RawInfoRequest('generic','Read any available context',('transcript','filing')),company_id='synthetic',identity={'ticker':'TEST'},as_of=NOW)
        self.assertEqual(result.status,'resolved');self.assertEqual([d.document_id for d in result.documents],['synthetic-filing'])
        self.assertEqual(client.calls,[]);self.assertEqual(resolver.budget.run_requests,2)
        self.assertTrue(any(e.details.get('reason')=='historical_data_unavailable' for e in result.events))

    def test_legacy_date_and_quarter_end_cannot_materialize_DocumentRecord(self):
        for item in ({'id':'synthetic-id','date':'2024-12-01'}, {'id':'synthetic-id','year':2024,'quarter':3}):
            with self.subTest(item=item):
                class Client:
                    calls=[]
                    def transcript_list(self,symbol):self.calls.append('list');return {'transcripts':[item]}
                    def transcript(self,ident):self.calls.append('body');return {'content':'Partial body is not proof.'}
                c=Client();warnings=[]
                result=legacy._transcript_documents_for_candidate(SimpleNamespace(max_transcripts_per_symbol=2),SimpleNamespace(symbol='TEST',inflection_date=NOW.date()),context_start=date(2024,1,1),created_at=NOW,finnhub_client=c,warnings=warnings)
                self.assertEqual(result,[]);self.assertEqual(c.calls,[])
    def _raw_cache(self,source,bodies,invoke):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);inner=BottomHTTP(bodies)
            def native(inner):
                ledger=RequestLedger(root/'ledger.jsonl')
                t=ManagedHttpTransport(source,DataCapability.TRANSCRIPTS,inner,RawDataCache(root/'cache'),ledger,SourceBudget(ledger,quotas={}),clock=lambda:NOW)
                client=AlphaVantageClient(TOKEN,transport=t) if source=='alpha_vantage' else FinnhubClient(TOKEN,transport=t)
                return client,ledger
            c,ledger=native(inner);first=invoke(c)
            self.assertEqual(len(inner.calls),len(first))
            filehash={str(p.relative_to(root)):hashlib.sha256(p.read_bytes()).hexdigest() for p in (root/'cache').rglob('*.json')}
            trap=BottomHTTP({});reopened,_=native(trap);second=invoke(reopened)
            self.assertEqual(first,second);self.assertEqual(trap.calls,[])
            self.assertEqual(filehash,{str(p.relative_to(root)):hashlib.sha256(p.read_bytes()).hexdigest() for p in (root/'cache').rglob('*.json')})
            statuses=[x.status for x in ledger.entries()]
            self.assertEqual(statuses,[RequestStatus.FETCHED]*len(first)+[RequestStatus.CACHE_HIT]*len(first))
            self.assertNotIn(TOKEN,(root/'ledger.jsonl').read_text())
            return first

    def test_native_alpha_raw_json_roundtrip_cache_reopen_is_not_admission(self):
        body={'symbol':'TEST','quarter':'2024Q3','transcript':[{'speaker':'CEO','content':'Cash {text} \\"literal\\" Ω'},{'speaker':'Analyst','content':'Question?'},{'speaker':'Operator','content':'Closing.'}],'provider_extra':{'preserve':True,'date':'1900-01-01'}}
        first=self._raw_cache('alpha_vantage',{'EARNINGS_CALL_TRANSCRIPT':body},lambda c:[c.earnings_call_transcript('test','2024Q3')])
        self.assertEqual(first,[body])

    def test_native_finnhub_list_and_body_raw_cache_remain_available(self):
        listing={'transcripts':[{'id':'synthetic-id','year':2024,'quarter':3}]};body={'id':'synthetic-id','content':[{'speech':'All raw bytes represented in JSON Ω {}'},{'speech':'Closing'}],'extra':[None,True,1,1.0]}
        first=self._raw_cache('finnhub',{'TEST':listing,'synthetic-id':body},lambda c:[c.transcript_list('test'),c.transcript('synthetic-id')])
        self.assertEqual(first,[listing,body])

if __name__=='__main__':
    with patch.object(socket,'socket',denied),patch.object(socket,'create_connection',denied),patch.object(UrllibJsonTransport,'get_json',denied),patch.object(LabelStore,'__init__',denied),patch.object(LabelStore,'load',denied):
        unittest.main(verbosity=2)
