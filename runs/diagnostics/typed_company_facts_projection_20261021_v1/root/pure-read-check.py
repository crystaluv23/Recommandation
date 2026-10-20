"""Read retained selected sources through the current pure projection only."""
import hashlib
import json
from pathlib import Path
import socket
from contextlib import ExitStack
from unittest.mock import patch

from stock_opportunity_agent.data.raw_info import RawInfoDocument, RawInfoStore
from stock_opportunity_agent.cases.label_store import LabelStore
from stock_opportunity_agent.research.evolution_core import _company_facts_context
from stock_opportunity_agent.research.evolution_signal_roles import (
    StructuredLLMSignalRunner, _single_llm_signal_projection,
)
from stock_opportunity_agent.signal_library import SignalSpec, SignalExecutor, LLMSignalBatchInput

OUT = Path(__file__).resolve().parent
OLD = Path('runs/diagnostics/default_llm_financial_read_20261021_v1/driver')
SNAPSHOT = Path('runs/diagnostics/reviewed_gpre_capture_snapshot_20261021_v1/stage/snapshot')
TAGS = {'CashAndCashEquivalentsAtCarryingValue': 98610000,
        'LiabilitiesCurrent': 325735000}
Q1 = 'rawcap:v1:64c9e4f193885e37ae497a75841bec6dec372f9fddf1ef7649710c28c40fc902'
bindings = {}


def read(path):
    content = Path(path).read_bytes()
    bindings[str(path)] = hashlib.sha256(content).hexdigest()
    return json.loads(content)


def forbidden(*args, **kwargs):
    raise AssertionError('Pure projection inspection forbids model, network, labels and execution')


with ExitStack() as guards:
    for owner, name in ((socket, 'socket'), (socket, 'create_connection'),
                        (RawInfoStore, 'append'), (LabelStore, '__init__'),
                        (SignalExecutor, 'execute_batch'), (SignalExecutor, 'prepare_inputs'),
                        (StructuredLLMSignalRunner, 'execute'),
                        (StructuredLLMSignalRunner, 'execute_many')):
        guards.enter_context(patch.object(owner, name, side_effect=forbidden))
    prior = read(OLD / 'result.json')
    plan = read(Path('runs/diagnostics/measurement_input_selection_20261021_v1/plan.json'))
    group = next(g for g in plan['groups'] if g['name'] == 'default_v6')
    definitions = [b for b in group['definition_bindings']
                   if '/cash_to_current_liabilities_ratio/versions/v1/' in b['path']]
    for bound in definitions:
        assert hashlib.sha256(Path(bound['path']).read_bytes()).hexdigest() == bound['sha256']
        bindings[bound['path']] = bound['sha256']
    spec = SignalSpec.from_dict(read(next(b['path'] for b in definitions if b['path'].endswith('spec.json'))))
    skill = Path(next(b['path'] for b in definitions if b['path'].endswith('skill.md'))).read_text()
    manifest = read(SNAPSHOT / 'reviewed_snapshot.json')
    needed = set(prior['native_selected_order']) | set(prior['counter_selected_order']) | {Q1}
    documents = {}
    for entry in manifest['documents']:
        if entry['document_id'] not in needed:
            continue
        path = SNAPSHOT / entry['path']
        assert hashlib.sha256(path.read_bytes()).hexdigest() == entry['sha256']
        document = RawInfoDocument.from_dict(read(path))
        assert document.document_id == entry['document_id']
        documents[document.document_id] = document
    assert set(documents) == needed
    source = documents[Q1]
    body = json.loads(source.content)
    expected = {fact['tag']: fact for fact in body['facts']
                if fact['tag'] in TAGS and fact['end'] == '2025-03-31' and fact['unit'] == 'USD'}
    assert set(expected) == set(TAGS)
    assert all(expected[tag]['value'] == value for tag, value in TAGS.items())
    context = _company_facts_context(source, max_content_chars=32000, query=spec.retrieval_policy.query)
    assert context is not None
    results = {}
    for name in ('native', 'counter'):
        selected = tuple(documents[key] for key in prior[name + '_selected_order'])
        assert len(selected) == 10
        rows, lineage = _single_llm_signal_projection(LLMSignalBatchInput(spec, selected, skill))
        visible = {}
        for tag, fact in expected.items():
            matches = [row for row in rows if row['document_id'] == Q1
                       and row.get('fact_context', {}).get('concept') == tag
                       and json.loads(row['exact_text']) == fact]
            visible[tag] = len(matches)
        assert sum(len(row['exact_text']) for row in rows) <= 32000
        assert all(row['exact_text'] in lineage[row['projection_id']].document.content for row in rows)
        results[name] = {'latest_operand_whole_literals_visible': visible,
                         'selected_order_unchanged': [d.document_id for d in selected] == prior[name + '_selected_order'],
                         'projection_count': len(rows),
                         'visible_characters': sum(len(row['exact_text']) for row in rows),
                         'fact_context_count': sum('fact_context' in row for row in rows)}
        (OUT / (name + '-projection.json')).write_text(json.dumps(rows, indent=2) + '\n')
    assert all(value == 0 for value in results['native']['latest_operand_whole_literals_visible'].values())
    assert all(value == 1 for value in results['counter']['latest_operand_whole_literals_visible'].values())
    assert all(hashlib.sha256(Path(path).read_bytes()).hexdigest() == digest
               for path, digest in bindings.items())
    for path in ('src/stock_opportunity_agent/research/evolution_core.py',
                 'src/stock_opportunity_agent/research/evolution_signal_roles.py', str(Path(__file__))):
        bindings[path] = hashlib.sha256(Path(path).read_bytes()).hexdigest()
    result = {'results': results, 'bindings': bindings, 'source_files_unchanged': True,
              'source_schema': body['schema_version'], 'helper_partial': context['partial'],
              'helper_omitted_concepts': context['omitted_concept_count'],
              'limits': ['pure local projection only; no transmitted prompt or model output',
                         'counter selection is previously frozen diagnostic; production ranking unchanged',
                         'no ratio, Signal execution, new source admission or complete-stage restore']}
    (OUT / 'actual-read-result.json').write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps(result['results']))
