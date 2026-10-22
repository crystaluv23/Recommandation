"""Native pre-dispatch no-progress guard has zero answered usage; no receipt authored."""
exec(Path(__file__).with_name('native_review_v2.py').read_text().split("with patch.object(socket,")[0])
from stock_opportunity_agent.research.evolution_core import CandidateExecutionRejected
c=client('native-no-progress');m=MiningAgentRoleModel(c,max_request_tokens=32768,max_total_tokens=98304,max_calls=6,max_output_tokens=2000);v=view()
with c.correction_chain(stage='mining_controller_step'):
 p=pending(m,v)
 before={'calls':m.reserved_calls,'tokens':m.reserved_tokens}
 try:m.next_action(v)
 except CandidateExecutionRejected as e:
  error={'type':type(e).__name__,'usage':{'llm_calls':e.usage.llm_calls,'tokens':e.usage.tokens},'message':str(e)}
 else:raise AssertionError('native same-request guard did not reject')
after={'calls':m.reserved_calls,'tokens':m.reserved_tokens}
save('predispatch-result',{'before':before,'after':after,'error':error,'pass':before==after,'receipts':len(list(c.local_role_exchange.root.glob('receipts/*.json'))),'source_bindings':[{'path':p,'sha256':hashlib.sha256((R/p).read_bytes()).hexdigest()} for p in ('src/stock_opportunity_agent/research/mining_role_model.py','src/stock_opportunity_agent/research/evolution_transport.py')],'evidence':'native pre-dispatch synthetic fixture, zero authored answers'})
print(json.dumps({'before':before,'after':after,'pass':before==after,'error':error}))
