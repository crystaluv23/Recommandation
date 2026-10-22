"""Bind default native request bytes against the frozen original implementation."""
from pathlib import Path
exec(Path(__file__).with_name('native_review_v3.py').read_text().split("with patch.object(socket,")[0])
import importlib.util,importlib.machinery
oldpath=O/'baseline-mining_role_model.py.txt';loader=importlib.machinery.SourceFileLoader('independent_frozen_original_mining_role',str(oldpath));spec=importlib.util.spec_from_loader(loader.name,loader);old=importlib.util.module_from_spec(spec);loader.exec_module(old)
v=view();c1=client('old');c2=client('new');p1=pending(old.MiningAgentRoleModel(c1),v);p2=pending(MiningAgentRoleModel(c2),v);q1=request(c1,p1);q2=request(c2,p2);assert q1==q2;assert p1['request_hash']==p2['request_hash']
save('default-comparison-result',{'pass':True,'exact_request_hash':p1['request_hash'],'full_requests_identical':True,'frozen_original_role_sha256':hashlib.sha256(oldpath.read_bytes()).hexdigest(),'current_role_sha256':hashlib.sha256((R/'src/stock_opportunity_agent/research/mining_role_model.py').read_bytes()).hexdigest(),'external_API':0,'answers':0,'scope':'native default exact-request comparison only'})
print(json.dumps({'pass':True,'exact_request_hash':p1['request_hash']}))
