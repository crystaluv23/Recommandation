"""Native profile resource-stop propagation without any evaluated role answer."""
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
import run_classification_consumer_stage as stage

with stage.guards():
    inputs,protected=stage.historical.authorities()
with TemporaryDirectory() as d, patch.object(stage,'ROOT',Path(d)):
    root=Path(d); c=stage.contract(); reached=[]
    def predictor_called(*args,**kwargs):
        reached.append('predictor'); raise AssertionError('prediction after approved allowance stop')
    with patch.object(stage,'ALLOWANCE',0), stage.guards(), patch.object(stage.LLMBlindPredictor,'predict',predictor_called):
        try:stage.native(inputs,c,stage.client_for(c))
        except stage.ApprovedAllowanceStop:pass
        else:raise AssertionError('native did not propagate profile terminal stop')
    assert not reached
    assert not list(root.rglob('inbox/*.json'))
    assert not (root/'prediction-sink.json').exists()
    # Supervisor must record terminal failure and reject a second resume.
    def stop_native(*args):raise stage.ApprovedAllowanceStop('independent terminal fixture')
    with patch.object(stage,'verify',return_value=(inputs,c)), patch.object(stage,'native',stop_native):
        try:stage.resume()
        except stage.ApprovedAllowanceStop:pass
        else:raise AssertionError('supervisor swallowed stop')
    assert stage.read_json(root/'failure.json')['type']=='ApprovedAllowanceStop'
    try:stage.resume()
    except stage.ValidationError as e:assert 'terminal' in str(e)
    else:raise AssertionError('terminal failure reopened')
print(json.dumps({'native_core_propagates_approved_allowance_stop':True,'predictor_called_after_stop':False,'production_inboxes':0,'supervisor_persists_terminal_failure':True,'terminal_reentry_refused':True,'evaluated_role_answers':0,'external_API':0,'labels':0},indent=2))
