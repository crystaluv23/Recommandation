"""Reconstruct a completed consumer in a throwaway copy; never resume its stage."""
from pathlib import Path
import shutil
import tempfile
from unittest.mock import patch

import run_financial_context_consumer_stage as consumer
from stock_opportunity_agent.research.evolution_transport import ExactResponseCache
from stock_opportunity_agent.research.local_role_exchange import LocalRoleExchange, _immutable

source = consumer.ROOT
inputs, contract = consumer.verify()
if not (source / 'completion.json').is_file():
    raise AssertionError('only completed artifact reconstruction is supported')
before = consumer.initial.files(source)
load = ExactResponseCache.load
receive = LocalRoleExchange.receive
reads = []

def cache_only(self, request_hash):
    value = load(self, request_hash)
    if value is None:
        raise AssertionError('cache miss: new response/dispatch is forbidden')
    reads.append(request_hash)
    return value

def receipt_only(self, request, *, accounting_tokens, allow_dispatch=True):
    if allow_dispatch:
        raise AssertionError('new model handoff is forbidden')
    return receive(self, request, accounting_tokens=accounting_tokens, allow_dispatch=False)

with tempfile.TemporaryDirectory() as directory:
    restored = Path(directory) / 'read-only-copy'
    shutil.copytree(source, restored)
    copied_before = {str(Path(r['path']).relative_to(restored)):r['sha256']
                     for r in consumer.initial.files(restored)}
    with patch.object(consumer, 'ROOT', restored), consumer.guards(), \
            patch.object(ExactResponseCache, 'load', cache_only), \
            patch.object(LocalRoleExchange, 'receive', receipt_only), \
            patch.object(LocalRoleExchange, 'submit', consumer.forbidden):
        try:
            consumer.native(inputs, contract, consumer.client_for(contract))
        except consumer.ConsumerBoundary:
            pass
        else:
            raise AssertionError('reconstruction did not stop before truth')
    copied_after = {str(Path(r['path']).relative_to(restored)):r['sha256']
                    for r in consumer.initial.files(restored)}
    if copied_after != copied_before:
        raise AssertionError('reconstruction changed copied artifacts')
consumer.initial.check(before)
consumer.verify()
value = {'state':'read_only_cache_reconstruction_verified',
    'unchanged_stage_files':len(before), 'cache_reads':reads,
    'unique_existing_receipts':len(set(reads)), 'new_handoffs':0,
    'new_external_API':0, 'labels':0, 'prior_inclusive_usage':consumer.read_json(source/'prediction-sink.json')['combined_case_usage'],
    'limitation':'Throwaway-copy reconstruction only, not OS interruption, business continuation or new model behavior.'}
_immutable(consumer.BASE / 'cache-reconstruction.json', value)
print(value)
