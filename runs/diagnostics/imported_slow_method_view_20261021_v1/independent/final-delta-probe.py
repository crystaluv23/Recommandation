"""Recheck only the scoped legacy-prior revision after the fixed suite."""
import ast
from contextlib import ExitStack
import hashlib
import json
from pathlib import Path
import socket
import unittest
from typing import Mapping, Iterable, Any
from unittest.mock import patch

from stock_opportunity_agent.research import signal_evolution as native
from stock_opportunity_agent import signal_library
from stock_opportunity_agent.cases.label_store import LabelStore
from stock_opportunity_agent.data.raw_info import RawInfoStore
from stock_opportunity_agent.research.evolution_transport import StructuredRoleClient
from tests.test_structured_reflection_roles import SlowAuthoredBriefTests

ROOT=Path(__file__).resolve().parent
REPO=ROOT.parents[3]
SOURCE=REPO/'src/stock_opportunity_agent/research/signal_evolution.py'
EXPECTED='23b036dfd4a116dba7518355210df66fefd5f880e69e03a9db63ae911bc4598f'
sha=lambda p:hashlib.sha256(Path(p).read_bytes()).hexdigest()

if __name__=='__main__':
    assert sha(SOURCE)==EXPECTED
    old=ast.parse((ROOT/'original-1e87-signal_evolution.py.txt').read_text())
    new=ast.parse(SOURCE.read_text())
    old_node=next(n for n in old.body if isinstance(n,ast.FunctionDef) and n.name=='_scoped_slow_method_deltas')
    new_node=next(n for n in new.body if isinstance(n,ast.FunctionDef) and n.name=='_scoped_slow_method_deltas')
    old.body.remove(old_node);new.body.remove(new_node)
    assert ast.dump(old)==ast.dump(new)
    ns={'Mapping':Mapping,'Iterable':Iterable,'Any':Any,
        '_slow_memory_roles':native._slow_memory_roles}
    exec(compile(ast.Module(body=[old_node],type_ignores=[]),'isolated-old-scope','exec'),ns)
    legacy={'cycle_id':1,'status':'appended','processed_feedback_refs':['old-source'],
        'episode_reflections':[{'episode_ref':'e1','source_refs':['old-source'],
            'reflection':'Exact authored old detail.','brief':'Old brief.','kind':'hypothesis'}],
        'lesson_additions':[]}
    unrelated={'new-source':{'visible_to':sorted(native._SLOW_SOURCE_ROLES)}}
    assert ns['_scoped_slow_method_deltas']([legacy],source_catalog=unrelated,role_scope='H1')==[]
    assert native._scoped_slow_method_deltas([legacy],source_catalog=unrelated,role_scope='H1')==[legacy]
    modern={**legacy,'schema_version':'slow-memory-v1','model_view_manifest':{'included_refs':['old-source']}}
    assert native._scoped_slow_method_deltas([modern],source_catalog=unrelated,role_scope='H1')==[]
    hidden={'old-source':{'visible_to':['Update','reflection']}}
    assert native._scoped_slow_method_deltas([modern],source_catalog=hidden,role_scope='H1')==[]
    assert native._scoped_slow_method_deltas([modern],source_catalog=hidden,role_scope='Update')==[modern]
    public={'old-source':{'visible_to':sorted(native._SLOW_SOURCE_ROLES)}}
    assert native._scoped_slow_method_deltas([modern],source_catalog=public,role_scope='H1')==[modern]
    assert native._scoped_slow_method_deltas([{**legacy,'schema_version':'slow-memory-v1'}],source_catalog=unrelated,role_scope='H1')==[]
    assert native._scoped_slow_method_deltas([{**legacy,'model_view_manifest':{'included_refs':['old-source']}}],source_catalog=hidden,role_scope='H1')==[]
    calls=[]
    def forbidden(*args,**kwargs):
        calls.append('forbidden');raise AssertionError('forbidden live dependency')
    with ExitStack() as stack:
        for owner,name in ((socket,'socket'),(socket,'create_connection'),(LabelStore,'load'),
                (LabelStore,'__init__'),(RawInfoStore,'__init__'),(signal_library.SignalExecutor,'execute_batch'),
                (signal_library.SignalRegistry,'freeze'),(signal_library.SignalRegistry,'audit_capabilities'),
                (StructuredRoleClient,'complete_json'),(StructuredRoleClient,'complete_json_with_token_scores'),
                (StructuredRoleClient,'complete_binary_token_with_scores')):
            stack.enter_context(patch.object(owner,name,forbidden))
        suite=unittest.TestSuite([SlowAuthoredBriefTests('test_slow_live_briefs_keep_originals_and_resolve_through_existing_reader')])
        result=unittest.TextTestRunner(verbosity=2).run(suite)
        assert result.wasSuccessful()
    assert calls==[] and sha(SOURCE)==EXPECTED
    out={'status':'PASS_final_legacy_delta_and_native_original_regression',
        'source_sha256':EXPECTED,'only_AST_changed_function':'_scoped_slow_method_deltas',
        'old_1e87_legacy_unrelated_catalog_filter_red':True,'new_legacy_scope_positive':True,
        'modern_unknown_and_hidden_rejected':True,'modern_public_and_Update_positive':True,
        'one_missing_identity_field_not_legacy_bypass':True,'native_original_regression_methods':1,
        'forbidden_calls':0,'live_models':0,'Signal_apply':0,'GET':0,'LabelStore':0}
    (ROOT/'final-delta-results.json').write_text(json.dumps(out,indent=2)+'\n')
    print(json.dumps(out,indent=2))
