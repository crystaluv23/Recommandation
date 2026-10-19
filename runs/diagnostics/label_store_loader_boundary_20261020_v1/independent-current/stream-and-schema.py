"""Independent tiny synthetic evaluation-only archive boundary probes; zero network."""
from pathlib import Path
from copy import deepcopy
from datetime import date
import json, hashlib, tempfile
import stock_opportunity_agent.cases.label_store as loader
from stock_opportunity_agent.data.json_stream import StreamingJSONReader
from stock_opportunity_agent.research.evolution_dataset import _StreamingJSONReader
from scripts.replay_incremental_reflection_memory import deny_network
REPO=Path('/Users/l/Project/Recommandation')
ROOT=Path(__file__).resolve().parent
old=json.loads((ROOT.parent/'original-counterexamples.json').read_text())
archive=old['fixture_archive']; bars=archive['bars_by_symbol']['DEMO']
records,_=loader.build_label_records({'DEMO':bars},[('cik_00000042','2025-01-15')],{'cik_00000042':'DEMO'})
rows=[]
def run(name,body,accept=False,selected=None,chunk=7):
    with tempfile.TemporaryDirectory(prefix='independent-label-stream-') as td:
        base=Path(td); ap=base/'archive.json'; ap.write_bytes(body); root=base/'store'
        loader.write_label_store(root,records=selected or records,archive_path=ap,archive_sha256=hashlib.sha256(body).hexdigest(),created_at='2026-10-20T00:00:00Z')
        class SmallReader(StreamingJSONReader):
            def __init__(self,path,**kw):super().__init__(path,chunk_size=chunk,**kw)
        original=loader.StreamingJSONReader; loader.StreamingJSONReader=SmallReader
        row={'case':name,'chunk_size_characters':chunk,'expected':'accepted' if accept else 'rejected','archive_sha256':hashlib.sha256(body).hexdigest(),'archive_bytes':len(body)}
        try:
            store=loader.LabelStore.load(root)
            actual=[store.record(*r.key).to_dict() for r in (selected or records)]
            assert actual==[r.to_dict() for r in (selected or records)]
            row.update(actual='accepted',record_count=len(store))
        except Exception as e:row.update(actual='rejected',error_type=type(e).__name__,error=str(e).replace(str(base),'@TMP@'))
        finally:loader.StreamingJSONReader=original
        row['pass']=row['actual']==row['expected']; rows.append(row)

compact=json.dumps(archive,ensure_ascii=False,separators=(',',':'))
barjson=json.dumps(bars,separators=(',',':'))
with deny_network() as net:
    for size in [1,2,7,64,1024]:
        rich=deepcopy(archive);rich['unicode_note']='合法é汉字𠮷';rich['long_note']='x'*2048
        raw=(json.dumps(rich,ensure_ascii=False,indent=1)+'\n\t\r\n').replace('\n','\r\n').encode('utf8')
        run('legal_CRLF_UTF8_exact_SHA_chunk_'+str(size),raw,True,chunk=size)
        with tempfile.TemporaryDirectory() as td:
            p=Path(td)/'a';p.write_bytes(raw);r=StreamingJSONReader(p,chunk_size=size,with_hash=True,strict_whitespace=True)
            try:
                parsed=r.decode();r.finish();assert parsed==rich;assert r.content_sha256==hashlib.sha256(raw).hexdigest()
            finally:r.close()
    run('top_trailing_comma', ('{"bars_by_symbol":{"DEMO":'+barjson+'},}').encode())
    run('symbol_trailing_comma', ('{"bars_by_symbol":{"DEMO":'+barjson+',}}').encode())
    run('array_trailing_comma', ('{"bars_by_symbol":{"DEMO":'+barjson[:-1]+',]}}').encode())
    for name,s in [('NBSP_leading','\u00a0'+compact),('NBSP_after_colon',compact.replace(':',':\u00a0',1)),('NBSP_between_symbols','{"bars_by_symbol":{\u00a0"DEMO":'+barjson+'}}'),('NBSP_trailing',compact+'\u00a0'),('vertical_tab_leading','\v'+compact),('form_feed_trailing',compact+'\f')]:run(name,s.encode())
    for name,s in [('duplicate_required_symbol','{"bars_by_symbol":{"DEMO":'+barjson+',"DEMO":'+barjson+'}}'),('duplicate_root_key','{"bars_by_symbol":{"DEMO":'+barjson+'},"bars_by_symbol":{"DEMO":'+barjson+'}}'),('bad_tail_junk',compact+'junk'),('second_JSON_value',compact+' {}'),('missing_final_brace',compact[:-1]),('missing_symbol_brace',compact[:-2]),('invalid_UTF8',None)]:run(name,s.encode() if s is not None else compact.encode()+b'\xff')
    multi=deepcopy(archive);multi['bars_by_symbol']['OTHER']=deepcopy(bars)
    rs,ex=loader.build_label_records(multi['bars_by_symbol'],[('cik_00000042','2025-01-15'),('cik_00000042','2025-01-14'),('cik_00000043','2025-01-15')],{'cik_00000042':'DEMO','cik_00000043':'OTHER'});assert not ex and len(rs)==3
    run('legal_multiple_symbols_and_same_symbol_two_asofs',json.dumps(multi).encode(),True,rs)
    absent=deepcopy(multi);del absent['bars_by_symbol']['OTHER'];run('one_of_three_records_symbol_unmatched',json.dumps(absent).encode(),False,rs)
    changed=deepcopy(multi);changed['bars_by_symbol']['OTHER'][80]['adjusted_close']=1000;run('second_symbol_record_recalculation_mismatch',json.dumps(changed).encode(),False,rs)
    for name,mut in [('selected_bar_bool',lambda x:x[0].update(adjusted_close=True)),('selected_bar_string',lambda x:x[0].update(adjusted_close='100')),('duplicate_selected_date',lambda x:x.append(deepcopy(x[0]))),('mismatched_row_symbol',lambda x:x[0].update(symbol='OTHER')),('noncanonical_date',lambda x:x[0].update(as_of_date='20250106'))]:
        changed=deepcopy(archive);mut(changed['bars_by_symbol']['DEMO']);run(name,json.dumps(changed).encode())
    assert _StreamingJSONReader is StreamingJSONReader
    with tempfile.TemporaryDirectory() as td:
        p=Path(td)/'legacy';p.write_text('\u00a0{"value":1}')
        r=_StreamingJSONReader(p,chunk_size=1)
        try:assert r.decode()=={'value':1};r.finish()
        finally:r.close()
paths=['src/stock_opportunity_agent/cases/label_store.py','src/stock_opportunity_agent/cases/outcomes.py','src/stock_opportunity_agent/data/json_stream.py','src/stock_opportunity_agent/research/evolution_dataset.py','spec/src/stock_opportunity_agent/cases/outcomes.md','spec/src/stock_opportunity_agent/data/json_stream.md']
out={'scope':'Tiny rehashed synthetic archives only. No real label store/archive/roles/network read or run. Loader deterministic schema/recompute door only, not CIK/provider/source qualification.','cases':rows,'all_passed':all(x['pass'] for x in rows),'direct_stream_hash_assertions':5,'legacy_reader_alias_and_default_behavior_preserved':True,'network_attempts':net['network_attempts'],'bindings':{p:hashlib.sha256((REPO/p).read_bytes()).hexdigest() for p in paths},'script_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest()}
p=ROOT/'stream-and-schema-results.json';assert not p.exists();p.write_text(json.dumps(out,indent=2,ensure_ascii=False)+'\n')
print(json.dumps({'cases':len(rows),'all_passed':out['all_passed'],'failures':[x for x in rows if not x['pass']],'network_attempts':out['network_attempts'],'bindings':out['bindings']},indent=2))
