"""One native Reflect serialization capture, never a fresh research/model stage.

Real saved results flow through Controller and anonymous StructuredRoleClient.
The first request_ready raises BaseException before cache/receive/dispatch.
Explicit empty-finalize state/default Plan prove serialization only; no need ownership is authored.
"""
from contextlib import ExitStack
from datetime import datetime, timezone
import argparse
import hashlib
import json
from pathlib import Path
import socket
import ssl
import subprocess
from unittest.mock import patch
import urllib.request

from diagnose_executed_answer_scope import StageContract
import run_minimal_rounds as minimal
from stock_opportunity_agent.artifacts import canonical_json_hash
from stock_opportunity_agent.cases.label_store import LabelStore
from stock_opportunity_agent.data.raw_info import RawInfoDocument, RawInfoStore
from stock_opportunity_agent.llm import get_model
from stock_opportunity_agent.research.evolution_core import ResearchDecision, ResearchState, default_information_plan
from stock_opportunity_agent.research.evolution_plan_roles import LLMResearchController
from stock_opportunity_agent.research.evolution_transport import (
    ExactResponseCache, ExternalAttemptLedger, StructuredRoleClient,
)
from stock_opportunity_agent.research.local_role_exchange import LocalRoleExchange
from stock_opportunity_agent.signal_library import SignalBatchResult, SignalExecutor, SignalResult

ROOT = Path(__file__).resolve().parent
REPO = ROOT.parents[3]
OUTPUT = ROOT / 'execution-v2'


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def read(path):
    return json.loads(Path(path).read_bytes())


def write(path, data):
    with Path(path).open('x', encoding='utf-8') as handle:
        json.dump(data, handle, sort_keys=True, indent=2, ensure_ascii=False, allow_nan=False)
        handle.write('\n')
        handle.flush()
        import os
        os.fsync(handle.fileno())


class RequestReadyBoundary(BaseException):
    """A deliberate pre-cache/pre-receive boundary, not a role response."""


def capture(expected_contract_sha, expectations, expected_expectations_sha):
    contract_path = ROOT / 'contract-v2.json'
    if sha(contract_path) != expected_contract_sha:
        raise ValueError('contract bytes differ')
    contract = read(contract_path)
    if sha(expectations) != expected_expectations_sha:
        raise ValueError('independent pre-capture expectations bytes differ')
    if ({'path': str(Path(expectations).resolve()), 'sha256': expected_expectations_sha}
            != contract['pre_capture_expectations']):
        raise ValueError('independent expectations authority differs')
    # The independent file is a sealed audit input, never parsed into role payload.
    bindings = contract['source_bindings'] + contract['code_bindings']
    before = {item['path']: sha(item['path']) for item in bindings}
    if any(before[item['path']] != item['sha256'] for item in bindings):
        raise ValueError('frozen input/code bytes differ')
    if OUTPUT.exists():
        raise ValueError('capture is terminal and cannot be reentered')
    OUTPUT.mkdir()
    write(OUTPUT / 'execution-start.json', {
        'contract_sha256': expected_contract_sha,
        'expectations': {'path': str(Path(expectations).resolve()), 'sha256': expected_expectations_sha},
        'at': datetime.now(timezone.utc).isoformat(),
    })
    counts = {'request_ready': 0, 'pre_egress_calls': 0}
    forbidden = []

    def deny(name):
        def rejected(*args, **kwargs):
            forbidden.append(name)
            raise AssertionError('forbidden operation: ' + name)
        return rejected

    def progress(event):
        if event['event_type'] != 'request_ready':
            return
        counts['request_ready'] += 1
        if counts['request_ready'] != 1:
            raise AssertionError('only one native request journal is permitted')
        write(OUTPUT / 'request-ready.json', event)
        raise RequestReadyBoundary()

    try:
        raw_results = [read(item['path']) for item in contract['results']]
        selected = [raw_results[index] for index in contract['selected_indices']]
        results = tuple(SignalResult.from_dict(item) for item in selected)
        if any(canonical_json_hash(result.to_dict()) != canonical_json_hash(raw)
               for result, raw in zip(results, selected, strict=True)):
            raise ValueError('result restore changed complete canonical record')
        batch = SignalBatchResult(results=results, signal_calls=len(results))
        with ExitStack() as stack:
            targets = (
                (socket, 'create_connection'), (socket.socket, 'connect'),
                (urllib.request, 'urlopen'), (ExactResponseCache, 'load'),
                (LocalRoleExchange, 'receive'), (ExternalAttemptLedger, 'reserve'), (LabelStore, '__init__'),
                (LabelStore, 'load'), (LabelStore, 'ground_truth'), (LabelStore, 'record'),
                (RawInfoStore, '__init__'), (RawInfoStore, 'append'),
                (SignalExecutor, 'execute_batch'), (minimal, 'prepare'),
            )
            for target, name in targets:
                stack.enter_context(patch.object(target, name, deny(target.__name__ + '.' + name)))
            exchange = LocalRoleExchange(OUTPUT / 'exchange', max_calls=1)
            client = StructuredRoleClient(
                registration=get_model('independent-subagent'),
                contract=StageContract(contract), workspace=OUTPUT,
                ledger=ExternalAttemptLedger(OUTPUT / 'unused-external.json', max_attempts=1, max_total_cost=0.01),
                allow_external=False, environ={}, on_progress=progress,
                local_role_exchange=exchange,
            )
            native_complete = client.complete_json

            def observe(**kwargs):
                counts['pre_egress_calls'] += 1
                if counts['pre_egress_calls'] != 1:
                    raise AssertionError('only one native Reflect call is permitted')
                write(OUTPUT / 'pre-egress.json', kwargs)
                return native_complete(**kwargs)

            client.complete_json = observe
            controller = LLMResearchController(client)
            cutoff = datetime.fromisoformat(contract['prediction_time'])
            controller.set_evaluation_context(cutoff)
            controller.set_request_token_budget(131072)
            try:
                with client.anonymous_case(
                    aliases=(), company_id=contract['identity']['company_id'],
                    ticker=contract['identity']['ticker'], expand_aliases=False,
                ):
                    controller.reflect(default_information_plan(), ResearchState(decision=ResearchDecision.FINALIZE), batch)
            except RequestReadyBoundary:
                pass
            else:
                raise AssertionError('native capture did not stop at request_ready')
        journals = sorted((OUTPUT / 'requests').glob('*.json'))
        if len(journals) != 1 or counts != {'request_ready': 1, 'pre_egress_calls': 1}:
            raise AssertionError('native journal/call count differs')
        outgoing = read(journals[0])['request']
        user_message = next(row['content'] for row in outgoing['messages'] if row['role'] == 'user')
        payload = json.loads(user_message)
        rows = payload['signal_batch']
        evidence_catalog = {row['signal_ref']: row for row in payload['signal_evidence_ref_catalog']}
        checks = []
        for result, row in zip(results, rows, strict=True):
            measurement = result.measurement.to_dict()
            numeric = row['measurement_context']['numeric_measurement']
            checks.append({
                'signal_ref': result.ref,
                'ref_equal': row['signal_ref'] == result.ref,
                'state_equal': row['state'] == {'value': result.value.value, 'confidence': result.confidence},
                'coverage_equal': row['status']['coverage'] == result.coverage.value,
                'measurement_value_equal': numeric['value'] == measurement['value'],
                'measurement_unit_equal': numeric['unit'] == measurement['unit'],
                'measurement_period_equal': numeric['period'] == measurement['period'],
                'measurement_formula_equal': numeric['formula'] == measurement['formula'],
                'exact_claim_equal': row['exact_claim_if_adopted'] == result.interpretation,
                'evidence_indices_equal': evidence_catalog[result.ref]['supporting_evidence_indices'] == list(range(len(result.supporting_evidence)))
                    and evidence_catalog[result.ref]['counter_evidence_indices'] == list(range(len(result.counter_evidence))),
            })
        snapshot = Path(contract['snapshot']['root'])
        sources = {row['document_id']: row for row in read(snapshot / 'reviewed_snapshot.json')['documents']}
        operand_mapping = []
        for result_index, raw in enumerate(raw_results):
            ref = raw['signal_id'] + ':v' + str(raw['version'])
            for group, items in raw['evidence'].items():
                for evidence_index, evidence in enumerate(items):
                    bound = sources[evidence['document_id']]
                    path = snapshot / bound['path']
                    doc = RawInfoDocument.from_dict(read(path))
                    literal = evidence['exact_span']
                    start = doc.content.find(literal)
                    operand_mapping.append({
                        'signal_ref': ref, 'evidence_group': group, 'evidence_index': evidence_index,
                        'document_id': doc.document_id, 'content_hash': doc.content_hash,
                        'file_sha256': sha(path), 'literal_sha256': hashlib.sha256(literal.encode()).hexdigest(),
                        'offset': start, 'whole_literal_reachable': start >= 0,
                        'source_file_binding_equal': sha(path) == bound['sha256'],
                        'company_equal': doc.company_id == contract['identity']['company_id'],
                        'available_by_cutoff': doc.available_at <= cutoff,
                        'evidence_timestamp_by_cutoff': datetime.fromisoformat(evidence['timestamp']) <= cutoff,
                        'evidence_timestamp_equals_source': datetime.fromisoformat(evidence['timestamp']) == doc.available_at,
                        'in_selected_six': result_index in contract['selected_indices'],
                    })
        wire_text = json.dumps(outgoing, ensure_ascii=False)
        # Real native masking is observed, not inferred merely from anonymous_case.
        mask = {name: token not in wire_text for name, token in contract['identity'].items()}
        write(OUTPUT / 'mapping.json', {'selected_result_checks': checks, 'all_nine_operand_mapping': operand_mapping,
                                      'identity_token_absent': mask, 'role_payload_keys': sorted(payload)})
        after = {item['path']: sha(item['path']) for item in bindings}
        write(OUTPUT / 'bindings-before-after.json', {'before': before, 'after': after})
        result = {'status': 'captured_before_cache_and_receive', 'counts': counts,
                  'forbidden_calls': forbidden, 'source_code_bytes_unchanged': before == after,
                  'source_denominator': 9, 'selected_results': 6, 'operand_rows': len(operand_mapping),
                  'payload_has_no_oracle_or_verdict': not any(key in payload for key in ('oracle','comparisons','passed_unique','expected')),
                  'model_calls': 0, 'role_dispatches': 0, 'responses': 0,
                  'scope': 'Serialization only. No accepted GPRE prior, H_init, need ownership or fresh research semantics.'}
        write(OUTPUT / 'result.json', result)
        return result
    except BaseException as error:
        import traceback
        write(OUTPUT / 'failure.json', {'error_type': type(error).__name__, 'message': str(error),
                                     'trace': traceback.format_exc(), 'counts': counts, 'forbidden_calls': forbidden})
        raise


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--expected-contract-sha', required=True)
    parser.add_argument('--expectations', type=Path, required=True)
    parser.add_argument('--expected-expectations-sha', required=True)
    args = parser.parse_args()
    print(json.dumps(capture(args.expected_contract_sha, args.expectations, args.expected_expectations_sha), indent=2))
