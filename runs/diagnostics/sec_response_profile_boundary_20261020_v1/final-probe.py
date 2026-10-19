"""Targeted index-code family and preserved readonly source proof checks."""
import ast,hashlib,json,tempfile,gzip
from pathlib import Path
D=Path(__file__).resolve().parent;R=D.parents[2]
tree=ast.parse((D/'probe.py').read_text());nodes=[]
for n in tree.body:
 if isinstance(n,(ast.Import,ast.ImportFrom,ast.FunctionDef,ast.ClassDef)):nodes.append(n)
 elif isinstance(n,ast.Assign) and all(isinstance(t,ast.Name) and t.id in {'D','R'} for t in n.targets):nodes.append(n)
ns={'__file__':str(D/'probe.py')};exec(compile(ast.Module(body=nodes,type_ignores=[]),'independent-fixed-fixture-defs','exec'),ns)
Fixture,execute,reader,hashcontent=ns['Fixture'],ns['execute'],ns['reader'],ns['content_sha256']
def parent(f,text,code):
 f.rawbytes['parent']=text.encode();f.proofs[-1]['expected_content_hash']=hashcontent(text)
 f.proofs[0]['exhibit_type']=code;f.record['metadata']['exhibit_type']=code
report={'reader_sha256':hashlib.sha256((R/'src/stock_opportunity_agent/data/reviewed_snapshot.py').read_bytes()).hexdigest(),'controls':{}}
with tempfile.TemporaryDirectory() as tmp:
 base=Path(tmp)
 cases=[('same_crossreference_wrong_code','<table><tr><td>99.1</td><td><a href="aif.htm">Annual information; see Exhibit99.2 for financials</a></td></tr></table>','99.2',False),('same_crossreference_right_code','<table><tr><td>99.1</td><td><a href="aif.htm">Annual information; see Exhibit99.2 for financials</a></td></tr></table>','99.1',True),('ambiguous_multiple_links','<table><tr><td>99.1</td><td><a href="aif.htm">Annual information</a><a href="other.htm">Other</a></td></tr></table>','99.1',False),('ambiguous_multiple_code_cells','<table><tr><td>99.1</td><td>99.2</td><td><a href="aif.htm">Annual information</a></td></tr></table>','99.2',False),('uncertain_null_type','<div><a href="aif.htm">A linked body with no index code</a></div>',None,True),('wrong_accession_link','<table><tr><td>99.1</td><td><a href="../000000000225000999/aif.htm">Annual information</a></td></tr></table>','99.1',False)]
 for name,text,code,accepted in cases:
  f=Fixture(base/name,exhibit=True);parent(f,text,code);out=execute(f);assert out['accepted']==accepted,(name,out)
  report['controls'][name]=out
 f=Fixture(base/'bodychanged');f.rawbytes['body']=b'Changed raw body with rehashed receipt';out=execute(f);assert not out['accepted'];report['controls']['rehashed_actual_body_mutation']=out
 f=Fixture(base/'gzip');f.rawbytes['body']=gzip.compress(f.rawbytes['body']);f.entries['body']['response_headers']={'cOnTeNt-EnCoDiNg':'GZip'};out=execute(f);assert out['accepted'];report['controls']['gzip_case_insensitive_positive']=out
 f=Fixture(base/'drift');b=reader.materialize_reviewed_snapshot(f.save(),f.base/'view');s=reader.open_raw_info_store(b['root'],reviewed_snapshot=b);(f.base/'body.raw').write_bytes(b'drift')
 for name,op in [('refresh_raw_drift',s.refresh),('worker_raw_drift',s.snapshot)]:
  try:op();out={'rejected':False}
  except reader.ReviewedSourceRejected as e:out={'rejected':True,'type':type(e).__name__,'message':str(e)}
  assert out['rejected'];report['controls'][name]=out
p=D/'final-results.json';p.write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report,indent=2))
