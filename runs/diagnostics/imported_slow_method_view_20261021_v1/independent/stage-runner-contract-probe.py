"""Temporary native import contract location counterexample only."""
from dataclasses import replace
from pathlib import Path
import json
import tempfile

from stock_opportunity_agent.artifacts import canonical_json_hash
from stock_opportunity_agent.models import ValidationError
from stock_opportunity_agent.research.signal_tracking import imported_learning_events
from tests.evolution_runtime_test_support import make_contract

with tempfile.TemporaryDirectory() as temp:
    root=Path(temp).resolve();work=root/'workspace'
    path=work/'slow_history/manifest.json';path.parent.mkdir(parents=True)
    manifest={'schema_version':'slow-history-manifest-v2','learning_events':[]}
    identity=canonical_json_hash(manifest)
    path.write_text(json.dumps({'manifest_hash':identity,'manifest':manifest}))
    contract=replace(make_contract(),slow_history_manifest_hash=identity)
    contract.freeze(root/'run_contract.json')
    try:
        imported_learning_events(work)
    except ValidationError as error:
        assert str(error)=='imported learning events require a frozen run contract'
        failure=str(error)
    else:
        raise AssertionError('missing workspace contract unexpectedly accepted')
    contract.freeze(work/'run_contract.json')
    assert imported_learning_events(work)==()
    print(json.dumps({'scope':'native temporary importer only; not a stage or Engine run',
        'root_contract_only_native_failure':failure,
        'same_contract_in_actual_workspace_positive':True,
        'Signal':0,'models':0,'GET':0,'real_labels':0}))
