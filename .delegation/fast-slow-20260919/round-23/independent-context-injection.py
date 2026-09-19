"""Independent real orchestration check of per-case optional routing context."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
from datetime import timedelta
from tests.test_information_plan_engine import InformationPlanRuntimeTests
from tests.scheme_evolution_test_support import *

class ObservedSelector(OneSignalSelector):
    def __init__(self):
        self.dates = []
        self.seen = []
    def set_evaluation_context(self, prediction_time):
        self.dates.append(prediction_time)
    def select(self, *args, **kwargs):
        assert self.dates
        self.seen.append(self.dates[-1])
        return super().select(*args, **kwargs)

selector = ObservedSelector()
with tempfile.TemporaryDirectory() as directory:
    registry, store = InformationPlanRuntimeTests()._registry_and_store(directory)
    for when in (NOW, NOW + timedelta(days=1)):
        execute_information_plan(
            plan=default_information_plan(), company_id='winner_1',
            company_basic_source={}, prediction_time=when,
            signal_registry=registry.freeze(), signal_executor=SignalExecutor(registry.freeze(), store),
            controller=OneBatchController(), signal_agent=selector,
            predictor=FixedPredictor(), prediction_sink=lambda *args: 'pred',
            ground_truth_provider=lambda company_id: GroundTruth(2.5), limits=RuntimeLimits(),
        )
assert selector.dates == [NOW, NOW + timedelta(days=1)]
assert selector.seen == selector.dates
print('PASS: actual execute_information_plan injects each case date before select; reused selector sees refreshed date')
