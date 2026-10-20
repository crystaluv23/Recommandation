"""Freeze and run one independent native S5 fixture-author module only."""
from __future__ import annotations

import argparse
from contextlib import ExitStack, contextmanager
from copy import deepcopy
from datetime import datetime
import fcntl
import hashlib
import json
from pathlib import Path
import socket
from types import SimpleNamespace
from unittest.mock import patch

from diagnose_executed_answer_scope import StageContract
from stock_opportunity_agent.artifacts import atomic_write_json, canonical_json_hash as digest
from stock_opportunity_agent.cases.label_store import LabelStore
from stock_opportunity_agent.data.raw_info import RawInfoDocument, RawInfoStore
from stock_opportunity_agent.data.sec_company_facts import _source_cik
from stock_opportunity_agent.llm import get_model
from stock_opportunity_agent.models import ValidationError
from stock_opportunity_agent.research.evolution_transport import (
    ExternalAttemptLedger, StructuredOutputInvalid, StructuredRoleClient,
)
from stock_opportunity_agent.research.local_role_exchange import LocalRoleExchange, LocalRoleRequestPending
from stock_opportunity_agent.research.signal_evolution import SignalCandidateValidator, SignalEvolutionEngine
from stock_opportunity_agent.signal_library import FrozenSignalRegistry, SignalExecutor, SignalRegistry, SignalSpec

REPO = Path(__file__).resolve().parents[1]
STAGE_ROOT = REPO / 'runs/diagnostics/reviewed_fixture_author_stage_20261021_v1'
CATALOG = REPO / 'configs/signals_v1.json'
SPEC = REPO / 'spec/scripts/run_reviewed_fixture_author_stage.md'
STAGE = 'mining_candidate_materialize_tests'
CUTOFF = '2025-03-01T00:00:00+00:00'
AVAILABLE = '2025-02-16T00:00:00+00:00'
EXCLUDED = {'progress.json', 'completion.json', 'failure.json', '.stage.lock', 'exchange/.dispatch.lock'}


def read(path):
    """Read one exact saved JSON artifact."""
    return json.loads(Path(path).read_text(encoding='utf-8'))


def binding(path):
    """Hash bytes without interpreting source content."""
    path = Path(path).resolve()
    return {'path': str(path), 'sha256': hashlib.sha256(path.read_bytes()).hexdigest()}


def _root(root):
    root = Path(root).resolve()
    if root != STAGE_ROOT.resolve():
        raise ValidationError('fixture-author stage destination is fixed')
    return root


def _contract():
    return {'schema_version': 'reviewed-fixture-author-stage-v1', 'root': str(STAGE_ROOT.resolve()),
            'stage': STAGE, 'max_calls': 1, 'max_output_tokens': 4000,
            'limits': {'max_request_tokens': 131072, 'max_case_tokens': 131072,
                       'max_case_llm_calls': 1, 'max_structured_corrections': 1,
                       'structured_reasoning_token_reserve': 0},
            'module_only': True, 'external_llm_api_calls': 0}


def _inputs():
    entry = next(row for row in read(CATALOG)['signals']
                 if row['spec']['signal_id'] == 'revenue_growth_yoy')
    spec = deepcopy(entry['spec'])
    spec.update(signal_id='fixture_author_revenue_growth', version=1)
    spec = SignalSpec.from_dict(spec).to_dict()
    rows = []
    for schema in ('typed', 'legacy'):
        for year, value in ((2023, 120), (2024, 150)):
            fact = {'start': f'{year}-01-01', 'end': f'{year}-12-31',
                    'filed': '2025-02-15', 'form': '10-K'}
            if schema == 'typed':
                fact.update(taxonomy='us-gaap', tag='Revenues', unit='USD', value=value)
            else:
                fact['val'] = value
            rows.append({'exact_span': json.dumps(fact, sort_keys=True, separators=(',', ':')),
                         'title': schema + ' SEC fact row', 'concept': 'Revenues',
                         'unit': 'USD', 'value': value,
                         'period': {'start': fact['start'], 'end': fact['end']}})
    rows += [{'exact_span': text} for text in (
        'Legacy SEC schema: cik identifies synthetic issuer 0000000001; facts.us-gaap.Revenues.units.USD is an array of the cited legacy val fact rows. Copy only legacy rows into this schema.',
        'Typed SEC schema: schema_version="sec-company-facts-document-v1"; cik identifies synthetic issuer 0000000001; filing_date="2025-02-15"; form="10-K"; facts is an array of the cited typed value fact rows. Copy only typed rows into this schema.')]
    evidence = {}
    for index, row in enumerate(rows):
        evidence[f'synthetic-{index}'] = {**row, 'document_ref': 'document-fixture:masked:financials:synthetic',
                                        'published_at': AVAILABLE, 'available_at': AVAILABLE}
    return {'accepted': {'spec': spec, 'skill': None},
            'candidate': {'evidence_refs': list(evidence), 'measurement': {
                'observable': 'annual revenue growth', 'kind': 'structured',
                'requirements': 'Author one separate executable fixture per cited SEC document schema. Each schema fixture uses one complete financial document containing both corresponding fact rows. Copy the corresponding schema fact rows verbatim; do not copy typed value rows into legacy val rows or conversely. Filing date 2025-02-15; available 2025-02-16 UTC; cutoff 2025-03-01 UTC. Apply the accepted spec and function unchanged.'}},
            'evidence': evidence}


def _expectations():
    return {'fixed_denominator': 2, 'schemas': ['legacy', 'typed'], 'positive_measurement': 0.25,
            'cik': '0000000001', 'cutoff': CUTOFF, 'available_at': AVAILABLE,
            'scope': 'native tests-author module only; not Mining, publication, reuse or MVP'}


def _code():
    paths = {Path(__file__).resolve(), SPEC, CATALOG,
             REPO / 'scripts/diagnose_executed_answer_scope.py',
             REPO / 'tests/test_reviewed_fixture_author_stage.py'}
    paths.update((REPO / 'src/stock_opportunity_agent').rglob('*.py'))
    paths.update((REPO / 'spec/src/stock_opportunity_agent').rglob('*.md'))
    return [binding(path) for path in sorted(paths)]


def _files(root):
    return [binding(path) for path in sorted(root.rglob('*')) if path.is_file()
            and path.relative_to(root).as_posix() not in EXCLUDED]


@contextmanager
def _guard(root):
    def forbidden(*args, **kwargs):
        raise ValidationError('fixture-author network/labels/source-write/seed-install forbidden')
    original_init = RawInfoStore.__init__
    original_append = RawInfoStore.append
    original_registry_init = SignalRegistry.__init__

    def store_init(store, *args, **kwargs):
        requested_root = args[0] if args else kwargs.get('root')
        if requested_root is not None:
            forbidden()
        return original_init(store, *args, **kwargs)

    def memory_append(store, document):
        if store.root is not None:
            forbidden()
        return original_append(store, document)

    def registry_init(registry, requested_root, *, candidate_root=None):
        if (Path(requested_root).resolve() != (root / 'isolated/signals').resolve()
                or candidate_root is None
                or Path(candidate_root).resolve() != (root / 'isolated/candidates').resolve()):
            forbidden()
        return original_registry_init(registry, requested_root, candidate_root=candidate_root)

    with ExitStack() as stack:
        stack.enter_context(patch.object(RawInfoStore, '__init__', store_init))
        stack.enter_context(patch.object(RawInfoStore, 'append', memory_append))
        stack.enter_context(patch.object(SignalRegistry, '__init__', registry_init))
        for target, name in ((socket, 'socket'), (socket, 'create_connection'),
                             (LabelStore, 'load'), (LabelStore, 'ground_truth'), (LabelStore, 'record'),
                             (SignalRegistry, 'install_catalog')):
            stack.enter_context(patch.object(target, name, forbidden))
        yield


def prepare(root):
    """Freeze a unique stage without dispatching or constructing a registry."""
    root = _root(root)
    if root.exists():
        raise ValidationError('fixture-author stage already exists')
    inputs = _inputs()
    record = {'contract': _contract(), 'inputs': inputs, 'expectations': _expectations(), 'code': _code()}
    root.mkdir(parents=True)
    for name in ('contract', 'inputs', 'expectations'):
        atomic_write_json(root / f'{name}.json', record[name])
    manifest = {'manifest_hash': digest(record), **record}
    atomic_write_json(root / 'manifest.json', manifest)
    return {'status': 'prepared_not_dispatched', 'manifest_hash': manifest['manifest_hash']}


def _verify(root):
    manifest = read(root / 'manifest.json')
    saved_hash = manifest.pop('manifest_hash')
    if digest(manifest) != saved_hash or digest(manifest['contract']) != digest(_contract()):
        raise ValidationError('fixture-author frozen contract changed')
    for name in ('contract', 'inputs', 'expectations'):
        if digest(read(root / f'{name}.json')) != digest(manifest[name]):
            raise ValidationError('fixture-author frozen input changed')
    if digest(manifest['inputs']) != digest(_inputs()) or digest(manifest['expectations']) != digest(_expectations()):
        raise ValidationError('fixture-author fixed input definition changed')
    if digest(manifest['code']) != digest(_code()):
        raise ValidationError('fixture-author code/source changed')
    return saved_hash, manifest


class _Budget:
    def __init__(self):
        self.request_hash = None
        self.reservation = 0

    def __call__(self, event):
        if event.get('event_type') != 'request_ready':
            return
        request = read(event['request_path'])['request']
        if request['stage'] != STAGE or request['max_output_tokens'] != 4000:
            raise ValidationError('fixture-author stage/correction/output drift')
        size = len(json.dumps(request['messages'], ensure_ascii=False, sort_keys=True,
                              separators=(',', ':')).encode()) + 4000
        if size > 131072 or self.request_hash is not None:
            raise ValidationError('fixture-author request/total ceiling exhausted')
        self.request_hash = event['request_hash']
        self.reservation = size


class _FirstAnswerCaller:
    def __init__(self, client):
        self.client = client

    def complete_json(self, **kwargs):
        # Preserve the native module payload; do not allow its generic L0 repair
        # to turn an invalid first JSON envelope into a successful stage answer.
        try:
            return self.client.complete_json(**kwargs)
        except StructuredOutputInvalid as error:
            raise ValidationError('fixture-author first JSON format rejected') from error


def _engine(root):
    engine = object.__new__(SignalEvolutionEngine)
    engine.registry = SignalRegistry(root / 'isolated/signals', candidate_root=root / 'isolated/candidates')
    engine.validator = SignalCandidateValidator(engine.registry, llm_runner=None)
    engine.slow_role_identity_guards = ()
    return engine


def _execute_fixture(spec, fixture, index):
    """Execute unchanged fixture documents through the real deterministic adapter."""
    company_id = fixture.get('company_id', f'candidate_fixture_{index + 1}')
    documents = tuple(RawInfoDocument.create(
        document_id=f'author-{index}-{number}', company_id=company_id,
        source_type=row['source_type'], published_at=datetime.fromisoformat(row.get('published_at', row['available_at'])),
        available_at=datetime.fromisoformat(row['available_at']), content=row['content'], metadata=row.get('metadata', {}))
        for number, row in enumerate(fixture['documents']))
    result = SignalExecutor(FrozenSignalRegistry(1, 'module-only', (spec,), {}),
                            RawInfoStore(documents=documents)).execute_batch(
                                (spec.ref,), company_id=company_id,
                                as_of=datetime.fromisoformat(fixture['as_of'])).results[0]
    return result


def _check_loaded(engine, signal_ref, inputs):
    spec, skill = engine.registry.load_candidate(signal_ref)
    tests = engine.registry.load_candidate_tests(signal_ref)
    if digest(spec.to_dict()) != digest(inputs['accepted']['spec']) or skill is not None:
        raise ValidationError('staged accepted module changed')
    found = set()
    results = []
    for index, fixture in enumerate(tests):
        result = _execute_fixture(spec, fixture, index)
        results.append(result.to_dict())
        if fixture['expected'] != 'positive' or result.value.value != 'positive':
            continue
        if result.measurement is None or abs(result.measurement.value - 0.25) > 1e-12:
            continue
        if fixture['as_of'] != CUTOFF:
            continue
        bodies = [json.loads(row['content']) for row in fixture['documents']]
        schemas = {'typed' if body.get('schema_version') == 'sec-company-facts-document-v1'
                   else 'legacy' if isinstance(body.get('facts'), dict) and 'us-gaap' in body['facts']
                   else 'unknown' for body in bodies}
        if len(schemas) != 1 or 'unknown' in schemas:
            continue
        for document_index, (row, body) in enumerate(zip(fixture['documents'], bodies)):
            if (_source_cik(body.get('cik')) != '0000000001'
                    or _source_cik(row.get('metadata', {}).get('cik')) != '0000000001'):
                continue
            if row['available_at'] != AVAILABLE or row.get('published_at', AVAILABLE) != AVAILABLE:
                continue
            if body.get('schema_version') == 'sec-company-facts-document-v1':
                facts = body['facts']
                filed = body.get('filing_date') == '2025-02-15' and body.get('form') == '10-K'
                schema = 'typed'
            else:
                facts = body['facts']['us-gaap']['Revenues']['units']['USD']
                filed = True  # The supplied canonical legacy rows own filed/form.
                schema = 'legacy'
            exact_rows = {item['exact_span'] for item in inputs['evidence'].values()
                          if item.get('title') == schema + ' SEC fact row'}
            actual_rows = {json.dumps(fact, sort_keys=True, separators=(',', ':')) for fact in facts}
            selected = {(item.document_id, item.exact_span) for item in result.supporting_evidence}
            expected_selected = {(f'author-{index}-{document_index}', span) for span in exact_rows}
            if filed and exact_rows <= actual_rows and selected == expected_selected:
                isolated = _execute_fixture(spec, {**fixture, 'documents': [row]}, index)
                if (isolated.value.value == 'positive' and isolated.measurement is not None
                        and abs(isolated.measurement.value - 0.25) <= 1e-12
                        and isolated.measurement.period_start == result.measurement.period_start == '2024-01-01'
                        and isolated.measurement.period_end == result.measurement.period_end == '2024-12-31'
                        and {(item.document_id, item.exact_span) for item in isolated.supporting_evidence}
                        == {(f'author-{index}-0', span) for span in exact_rows}):
                    found.add(schema)
    if found != {'legacy', 'typed'}:
        raise ValidationError('two-schema synthetic positive control incomplete')
    return {'signal_ref': signal_ref, 'loaded_tests': list(tests), 'results': results, 'schemas': sorted(found)}


def _terminal(root, name, manifest_hash, result):
    value = {'manifest_hash': manifest_hash, 'result': result, 'artifacts': _files(root)}
    value['seal'] = digest(value)
    atomic_write_json(root / name, value)


def resume(root):
    """Consume one answer or restore a sealed terminal module stage."""
    root = _root(root)
    with _guard(root), (root / '.stage.lock').open('a+') as lock:
        fcntl.flock(lock.fileno(), fcntl.LOCK_EX)
        manifest_hash, manifest = _verify(root)
        for name in ('completion.json', 'failure.json'):
            if (root / name).exists():
                terminal = read(root / name)
                seal = terminal.pop('seal')
                if digest(terminal) != seal or terminal['manifest_hash'] != manifest_hash or terminal['artifacts'] != _files(root):
                    raise ValidationError('fixture-author terminal artifact drift')
                return {**terminal['result'], 'restored_without_execution': True}
        budget = _Budget()
        client = StructuredRoleClient(registration=get_model('independent-subagent'), contract=StageContract(manifest['contract']),
                                      workspace=root, local_role_exchange=LocalRoleExchange(root / 'exchange', max_calls=1),
                                      ledger=ExternalAttemptLedger(root / 'unused_external_attempts.json', max_attempts=1, max_total_cost=.01),
                                      allow_external=False, environ={}, on_progress=budget)
        result = {'module_only': True, 'external_llm_api_calls': 0, 'labels_read': 0,
                  'stable_publications': 0, 'host_tokens': None, 'host_cost': None}
        try:
            engine = _engine(root)
            inputs = manifest['inputs']
            parsed, issues = engine._materialize_tests_module(
                inputs['candidate'], caller=_FirstAnswerCaller(client),
                evidence={key: SimpleNamespace(**row) for key, row in inputs['evidence'].items()},
                last_issues=[], seed='synthetic-module-only', accepted=deepcopy(inputs['accepted']))
            if issues or parsed is None:
                raise ValidationError('; '.join(issues) or 'tests module returned no candidate')
            audit = _check_loaded(engine, parsed[0], inputs)
            atomic_write_json(root / 'loaded-candidate.json', audit)
            result.update(status='module_completed_requires_independent_review', logical_reservation=budget.reservation,
                          candidate_ref=parsed[0], loaded_candidate=binding(root / 'loaded-candidate.json'))
            _terminal(root, 'completion.json', manifest_hash, result)
        except LocalRoleRequestPending as error:
            result.update(status='pending_independent_role', pending=error.pending)
        except Exception as error:
            result.update(status='terminal_failed', error_type=type(error).__name__, error=str(error),
                          logical_reservation=budget.reservation)
            _terminal(root, 'failure.json', manifest_hash, result)
        atomic_write_json(root / 'progress.json', result)
        return result


def submit(root, request_hash, agent_id):
    """Bind exactly one independently authored original answer without editing."""
    root = _root(root)
    with _guard(root), (root / '.stage.lock').open('a+') as lock:
        fcntl.flock(lock.fileno(), fcntl.LOCK_EX)
        _verify(root)
        if any((root / name).exists() for name in ('completion.json', 'failure.json')):
            raise ValidationError('fixture-author terminal stage cannot submit')
        pending = read(root / 'progress.json').get('pending', {})
        if request_hash != pending.get('request_hash'):
            raise ValidationError('fixture-author submission differs from pending request')
        return LocalRoleExchange(root / 'exchange', max_calls=1).submit(request_hash, agent_id=agent_id)


def main():
    """Prepare, resume or submit the one fixed tests-author stage."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, required=True)
    modes = parser.add_mutually_exclusive_group(required=True)
    for name in ('prepare', 'resume', 'submit'):
        modes.add_argument('--' + name, action='store_true')
    parser.add_argument('--request-hash')
    parser.add_argument('--agent-id')
    args = parser.parse_args()
    if args.prepare:
        result = prepare(args.root)
    elif args.submit:
        if not args.request_hash or not args.agent_id:
            parser.error('submit requires request-hash and actual agent-id')
        result = submit(args.root, args.request_hash, args.agent_id)
    else:
        result = resume(args.root)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
