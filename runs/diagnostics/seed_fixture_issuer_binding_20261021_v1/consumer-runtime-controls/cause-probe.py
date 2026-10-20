"""Two original positive producers, native executor; no runtime assertion edits."""
from contextlib import ExitStack
import hashlib
import json
from pathlib import Path
import socket
import tempfile
from unittest.mock import patch

from tests.test_information_plan_engine import InformationPlanRuntimeTests
from tests.scheme_evolution_test_support import (
    NOW, RawInfoDocument, RawInfoStore, SignalExecutor, sec_company_facts_content,
)
from stock_opportunity_agent.cases.label_store import LabelStore

OUT = Path(__file__).resolve().parent
rows = []
with ExitStack() as guards:
    for obj, name in ((socket, 'socket'), (socket, 'create_connection'),
                      (LabelStore, 'load'), (LabelStore, 'record')):
        guards.enter_context(patch.object(obj, name, side_effect=AssertionError('offline only')))
    with tempfile.TemporaryDirectory() as directory:
        registry, store = InformationPlanRuntimeTests()._registry_and_store(directory)
        snapshot = registry.freeze()
        # This second constructor preserves the exact shared-financials body,
        # identity and clocks in the original repeated-issuer test.
        shared = RawInfoDocument.create(document_id='shared_financials',
            company_id='shared_issuer', source_type='financials', published_at=NOW,
            available_at=NOW, content=sec_company_facts_content(
                ('2023-01-01', '2023-12-31', 100.0, '2024-02-01'),
                ('2024-01-01', '2024-12-31', 125.0, '2025-01-10')))
        for name, company, actual_store in (
            ('actual_registry_and_store', 'winner_1', store),
            ('exact_shared_constructor', 'shared_issuer', RawInfoStore(documents=(shared,))),
        ):
            result = SignalExecutor(snapshot, actual_store).execute_batch(
                ('revenue_growth_yoy:v1',), company_id=company, as_of=NOW).results[0]
            assert result.execution_status.value == 'validation_failed', result.to_dict()
            assert 'opaque company has no explicit issuer binding' in result.execution_error_message
            rows.append({'producer': name, 'result': result.to_dict()})
summary = {'original_test_sha256': hashlib.sha256((OUT/'original-test-source.py').read_bytes()).hexdigest(),
           'cause': 'Both intended numeric positives fail issuer validation before runtime Reflect/continuation behavior.',
           'rows': rows, 'GETs': 0, 'models': 0, 'labels': 0, 'real_store_writes': 0}
with (OUT/'original-cause-results.json').open('x') as handle:
    json.dump(summary, handle, indent=2); handle.write('\n')
print(json.dumps(summary, indent=2))
