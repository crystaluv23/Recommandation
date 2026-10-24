#!/usr/bin/env python3
"""Bound one native GPRE bootstrap/H_init; never enter the research tail.

The formal destination and budgets are profile constants. Temporary preflight
may explicitly replace ROOT in an importing test; CLI cannot rename the stage.
No oracle content is passed to a role. Local pending is a handoff, not a model
call or accepted research state.
"""
from __future__ import annotations

import argparse
from contextlib import ExitStack, contextmanager
from dataclasses import asdict, replace
from html import unescape
import json
from pathlib import Path
import re
import socket
import traceback
from unittest.mock import patch

from diagnose_executed_answer_scope import StageContract, binding, read_json
import run_reviewed_orientation_stage as orientation
from stock_opportunity_agent.artifacts import atomic_write_json, canonical_json_hash
from stock_opportunity_agent.data.raw_info import RawInfoStore
from stock_opportunity_agent.data.reviewed_snapshot import ReviewedRawInfoStore, open_raw_info_store
from stock_opportunity_agent.cases.label_store import LabelStore
from stock_opportunity_agent.llm import get_model
from stock_opportunity_agent.models import ValidationError
from stock_opportunity_agent.research.evolution_core import default_information_plan, RuntimeBudgetExceeded
from stock_opportunity_agent.research.evolution_transport import ExternalAttemptLedger, StructuredRoleClient
from stock_opportunity_agent.research.local_role_exchange import LocalRoleExchange, LocalRoleRequestPending
from stock_opportunity_agent.signal_library import SignalExecutor, SignalRegistry

REPO = orientation.REPO
ROOT = REPO / 'runs/diagnostics/gpre_native_initial_20261021_v1/stage'
SPEC = REPO / 'spec/scripts/run_gpre_native_initial_stage.md'
SOURCE_RESULT = REPO / 'runs/diagnostics/reviewed_gpre_capture_snapshot_20261021_v1/stage/result.json'
SOURCE_RESULT_SHA = '2c6e706bad8a63742f3f50b812d6e9aca6a4a27b7d557734ce2609c2e6580cfb'
SOURCE_MANIFEST_SHA = '47546fc9029270e59a99353ac37e73857f0a3bf455ef54fe1428d836116e0c5a'
GROUP_PLAN = REPO / 'runs/diagnostics/measurement_input_selection_20261021_v1/plan.json'
COMPANY = 'cik_0001309402'
CUTOFF = '2025-05-30T00:00:00+00:00'
LIMITS = {'max_request_tokens': 131072, 'max_case_tokens': 256000,
          'max_local_role_calls': 2, 'max_structured_corrections': 1,
          'structured_reasoning_token_reserve': 0}


def files(root):
    """Bind exact file bytes without interpreting any retrospective fields."""
    return [binding(p) for p in sorted(Path(root).rglob('*')) if p.is_file()]


def check(rows):
    for row in rows:
        binding(Path(row['path']), row['sha256'])


def unique(rows):
    values = {}
    for row in rows:
        if row['path'] in values and values[row['path']] != row:
            raise ValidationError('conflicting frozen binding')
        values[row['path']] = row
    return [values[key] for key in sorted(values)]


def code_bindings():
    return unique([*orientation._code_bindings(), binding(Path(__file__)), binding(SPEC),
                   binding(REPO / 'scripts/run_reviewed_orientation_stage.py')])


def identity(source):
    """Read the actual qualified SEC cover and market metadata, not a case label."""
    root = Path(source['root'])
    manifest = read_json(root / 'reviewed_snapshot.json')
    records = {r['document_id']: r for r in manifest['documents']}
    filing_row = records['sec:cik_0001309402:000130940225000089']
    path = root / filing_row['path']
    proof = binding(path, filing_row['sha256'])
    filing = read_json(path)
    content = filing['content']
    evidence = []
    values = {}
    for tag in ('EntityRegistrantName', 'TradingSymbol'):
        match = re.search(r'<[^>]+name=[\"\x27]dei:' + tag +
                          r'[\"\x27][^>]*>(.*?)</[^>]+>', content, re.I | re.S)
        if match is None:
            raise ValidationError('qualified SEC cover lacks exact issuer identity')
        values[tag] = unescape(re.sub('<[^>]*>', '', match.group(1))).strip()
        evidence.append({'tag': tag, 'literal': match.group(0), 'start': match.start(),
                         'end': match.end(), 'document': proof})
    if filing['company_id'] != COMPANY or filing['metadata']['cik'] != '0001309402':
        raise ValidationError('issuer cover identity mismatch')
    market = []
    for row in manifest['documents']:
        if row['document_id'].startswith('massive:' + COMPANY + ':market_data:'):
            document = read_json(root / row['path'])
            if document['metadata']['symbol'] != values['TradingSymbol']:
                raise ValidationError('SEC and market ticker disagree')
            market.append(binding(root / row['path'], row['sha256']))
    if not market:
        raise ValidationError('identity has no qualified market corroboration')
    name = values['EntityRegistrantName']
    aliases = [name, values['TradingSymbol']]
    # Only retain a shorter corporate name when it is also literal in this body.
    short = re.sub(r'\s+(?:INC\.?|CORPORATION|CORP\.?)$', '', name, flags=re.I)
    found = re.search(re.escape(short), content, re.I) if short != name else None
    if found:
        aliases.append(found.group(0))
    return ({'cik': '0001309402', 'ticker': values['TradingSymbol'],
             'company_name': name, 'identity_aliases': list(dict.fromkeys(aliases))},
            {'cover': evidence, 'market_documents': market})


def authorities():
    """Freeze current readable source bytes, with the existing qualified authority."""
    binding(SOURCE_RESULT, SOURCE_RESULT_SHA)
    result = read_json(SOURCE_RESULT)
    source = result['reviewed_source_snapshot']
    if source.get('manifest_sha256') != SOURCE_MANIFEST_SHA or source.get('store_type') != 'reviewed':
        raise ValidationError('qualified1780 authority differs')
    store = open_raw_info_store(source['root'], reviewed_snapshot=source)
    if store.acquisition_allowed or len(store.documents) != 1780:
        raise ValidationError('qualified source scope/capability differs')
    issuer, evidence = identity(source)
    group = next(g for g in read_json(GROUP_PLAN)['groups'] if g['name'] == 'latest_v12')
    check(group['definition_bindings'])
    originals = unique([binding(SOURCE_RESULT), binding(GROUP_PLAN),
                        *files(source['root']), *group['definition_bindings']])
    sample = {'sample_id': 'h01', 'source': 'gpre', 'company_id': COMPANY,
              'prediction_time': CUTOFF, 'identity': issuer}
    return {'sources': {'gpre': source}, 'sample': sample,
            'plan': default_information_plan().to_dict(), 'registry_group': group,
            'identity_provenance': evidence}, originals


@contextmanager
def guards():
    """Permit reviewed-memory parent initialization; deny all forbidden effects."""
    native_init = RawInfoStore.__init__
    def forbidden(*args, **kwargs):
        raise ValidationError('GPRE initial boundary forbids network/labels/Signal/source write/fresh freeze')
    def memory_only(self, root=None, documents=()):
        if root is not None or tuple(documents):
            forbidden()
        native_init(self)
    with ExitStack() as stack:
        for owner, name in ((socket, 'socket'), (socket, 'create_connection'),
                (LabelStore, '__init__'), (LabelStore, 'load'), (LabelStore, 'record'),
                (LabelStore, 'ground_truth'), (RawInfoStore, 'append'),
                (ReviewedRawInfoStore, 'append'), (SignalExecutor, 'execute_batch'),
                (SignalExecutor, 'prepare_inputs'), (SignalRegistry, 'freeze'),
                (SignalRegistry, 'register_stable'), (ExternalAttemptLedger, 'reserve')):
            stack.enter_context(patch.object(owner, name, forbidden))
        stack.enter_context(patch.object(RawInfoStore, '__init__', memory_only))
        yield


def prepare(*, expectations):
    """Prepare the one fixed destination without invoking a role or Signal."""
    if ROOT.exists():
        raise ValidationError('GPRE initial stage destination already exists')
    with guards():
        inputs, originals = authorities()
    contract = {'schema_version': 'gpre-native-initial-v1', 'backend': 'independent-subagent',
                'limits': LIMITS, 'runtime_limits': asdict(replace(orientation.LIMITS, max_llm_calls=3)),
                'fixed_denominator': 1, 'tail_forbidden': True,
                'neutral_path_byte_exact_author_handoff_required': True}
    manifest = {'root': str(ROOT), 'inputs_hash': canonical_json_hash(inputs),
                'contract_hash': canonical_json_hash(contract), 'source_files': originals,
                'code_files': code_bindings(), 'expectations': binding(Path(expectations))}
    check(manifest['source_files'] + manifest['code_files'])
    manifest['manifest_hash'] = canonical_json_hash(manifest)
    ROOT.mkdir(parents=True, exist_ok=False)
    for name, value in (('inputs', inputs), ('contract', contract), ('manifest', manifest)):
        atomic_write_json(ROOT / (name + '.json'), value)
    return {'manifest_hash': manifest['manifest_hash'], 'source_files': len(originals),
            'code_files': len(manifest['code_files']), 'role_requests': 0}


def verify():
    manifest = read_json(ROOT / 'manifest.json')
    digest = manifest.pop('manifest_hash')
    inputs = read_json(ROOT / 'inputs.json')
    contract = read_json(ROOT / 'contract.json')
    if (manifest['root'] != str(ROOT) or canonical_json_hash(manifest) != digest
            or canonical_json_hash(inputs) != manifest['inputs_hash']
            or canonical_json_hash(contract) != manifest['contract_hash']
            or contract['limits'] != LIMITS):
        raise ValidationError('GPRE initial frozen stage changed or relocated')
    check(manifest['source_files'] + manifest['code_files'] + [manifest['expectations']])
    return inputs, contract


class Budget:
    """Count one replayed native chain logically, including its one correction."""
    def __init__(self):
        self.requests = []
        self.total = 0

    def __call__(self, event):
        if event.get('event_type') != 'request_ready':
            return
        request = read_json(Path(event['request_path']))['request']
        if request['stage'] not in {'research_controller_initialize', 'research_controller_initialize_correction',
                                    'research_controller_initialize_patch_mechanics_correction'}:
            raise ValidationError('only H_init and its native correction may request an author')
        size = len(json.dumps(request['messages'], ensure_ascii=False, sort_keys=True,
                              separators=(',', ':')).encode('utf-8')) + request['max_output_tokens']
        if (size > LIMITS['max_request_tokens'] or self.total + size > LIMITS['max_case_tokens']
                or len(self.requests) >= LIMITS['max_local_role_calls']):
            raise RuntimeBudgetExceeded('GPRE initial frozen logical request/case ceiling')
        self.total += size
        self.requests.append({'request_hash': event['request_hash'], 'reservation': size})
        atomic_write_json(ROOT / 'request-reservations.json', {'requests': self.requests, 'total': self.total})


def resume():
    """Reach one pending request or persist accepted H_init, stopping the tail."""
    inputs, contract = verify()
    if (ROOT / 'failure.json').exists() or (ROOT / 'completion.json').exists():
        raise ValidationError('terminal GPRE initial stage cannot reenter')
    budget = Budget()
    try:
        with guards():
            candidates = ROOT / 'unused_candidates'
            candidates.mkdir(exist_ok=True)
            group = inputs['registry_group']
            before = files(group['root'])
            registry = SignalRegistry(group['root'], candidate_root=candidates)
            snapshot = registry.snapshot_from_refs(group['version'], tuple(group['refs']))
            if snapshot.registry_hash != group['registry_hash'] or before != files(group['root']):
                raise ValidationError('exact Registry definition snapshot drift')
            exchange = LocalRoleExchange(ROOT / 'exchange', max_calls=2)
            client = StructuredRoleClient(registration=get_model('independent-subagent'),
                contract=StageContract(contract), workspace=ROOT,
                ledger=ExternalAttemptLedger(ROOT / 'unused_external_attempts.json', max_attempts=1, max_total_cost=.01),
                local_role_exchange=exchange, allow_external=False, environ={}, on_progress=budget)
            orientation._run_initial(ROOT, inputs['sample'], default_information_plan(), inputs,
                                     contract, snapshot, client)
    except LocalRoleRequestPending as pending:
        verify()
        return {'status': 'pending', **pending.pending, 'logical_reservation': budget.total}
    except orientation.InitialBoundary:
        verify()
        result = {'status': 'accepted_initial_requires_independent_review', 'logical_reservation': budget.total,
                  'requests': budget.requests, 'initial_state': binding(ROOT / 'samples/h01/initial_state.json'),
                  'routing': 0, 'Signal_execution': 0, 'Reflect': 0, 'Predictor': 0, 'model_API': 0}
        atomic_write_json(ROOT / 'completion.json', result)
        return result
    except BaseException as exc:
        atomic_write_json(ROOT / 'failure.json', {'error_type': type(exc).__name__, 'error': str(exc),
                                                'traceback': traceback.format_exc()})
        raise


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    action = parser.add_mutually_exclusive_group(required=True)
    action.add_argument('--prepare', action='store_true')
    action.add_argument('--resume', action='store_true')
    action.add_argument('--submit')
    parser.add_argument('--expectations', type=Path)
    parser.add_argument('--agent-id')
    args = parser.parse_args()
    if args.prepare:
        if args.expectations is None:
            parser.error('--prepare requires --expectations')
        value = prepare(expectations=args.expectations)
    elif args.resume:
        value = resume()
    else:
        verify()
        if (ROOT / 'completion.json').exists() or (ROOT / 'failure.json').exists():
            raise ValidationError('terminal stage cannot accept a raw answer')
        value = LocalRoleExchange(ROOT / 'exchange', max_calls=2).submit(args.submit, agent_id=args.agent_id or '')
    print(json.dumps(value, ensure_ascii=False, sort_keys=True))


if __name__ == '__main__':
    main()
