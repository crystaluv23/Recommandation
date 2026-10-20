"""Read-only pre-prepare authority linkage probe; opens no source Store."""
import importlib.util
import json
import os
from pathlib import Path
import time

path=Path(__file__).with_name('run_native.py')
spec=importlib.util.spec_from_file_location('native_authority_probe',path)
m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
started=time.monotonic()
print(json.dumps({'pid':os.getpid(),'command':'read_authorities.py','runner':m.binding(path),
    'stage_exists_before':m.OUTPUT.exists()}),flush=True)
try:
    with m.bounded_operations():
        value=m.authorities()
    summary={'status':'verified_readonly','runner':m.binding(path),'head':m.head(),
        'source_bindings':len(value['source_bindings']),'code_bindings':len(value['code_bindings']),
        'definition_identity_fields':5,'definition_bindings':43,
        'financial_refs':len(value['oracle']['rows']),'original_snapshot_refs':len(value['group']['refs']),
        'stage_exists_after':m.OUTPUT.exists(),'wall_seconds':time.monotonic()-started,
        'operations':'No prepare/execute/Signal/source Store/global write/model/network/label calls.'}
except Exception as exc:
    summary={'status':'readonly_failure','error_type':type(exc).__name__,'error':str(exc),
        'runner':m.binding(path),'stage_exists_after':m.OUTPUT.exists(),'wall_seconds':time.monotonic()-started}
    m.write_new(path.with_name('read-authorities-result.json'),summary)
    print(json.dumps(summary),flush=True)
    raise
m.write_new(path.with_name('read-authorities-result.json'),summary)
print(json.dumps(summary),flush=True)
