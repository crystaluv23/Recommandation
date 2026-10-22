"""Independent pre-repair handoff controls; no models, external I/O or labels.

The sole real source is snapshot document 1179. All case/cohort and narrative
controls are explicitly synthetic; no business-stage acceptance is inferred.
"""
from dataclasses import asdict, replace
from datetime import datetime, timezone
import hashlib
import inspect
import json
from pathlib import Path
from types import SimpleNamespace

from stock_opportunity_agent.data.raw_info import RawInfoDocument, RawInfoStore
from stock_opportunity_agent.research.mining_agent_tools import project_facts_from_documents
from stock_opportunity_agent.research.mining_controller import LabelAwareMiningController
from stock_opportunity_agent.research.signal_evolution import SignalEvolutionEngine

ROOT = Path(__file__).resolve().parent
REPO = ROOT.parents[3]
NOW = datetime(2025, 5, 30, tzinfo=timezone.utc)


def case(company, suffix):
    # No realized label is read. The actual controller requires this attribute
    # even when passed an explicit synthetic label map.
    return SimpleNamespace(company_id=company, prediction_time=NOW,
                           case_id='synthetic-' + suffix,
                           ground_truth=SimpleNamespace(is_surge=False))


def controller(documents, cases=None):
    cases = cases or [case(documents[0].company_id, 'case')]
    pairs = [(f'case-{i:03}', c) for i, c in enumerate(cases, 1)]
    return LabelAwareMiningController(store=RawInfoStore(documents=documents),
        model=None, case_pairs=pairs, measurable_evidence_manifest={},
        signal_catalog=[], seed='discovery',
        label_map={ref: 'control' for ref, _ in pairs})


def action(c, name, **kwargs):
    raw = dict(action=name, rationale=['Synthetic structural review.'], **kwargs)
    c._validate_action_shape(raw)
    return c._execute(name, raw)


def proposal(refs, narrative=False):
    m = dict(observable='synthetic_review_observable', value_kind='numeric',
             normalization='Use the cited observation under its original units.')
    if narrative:
        m['value_kind'] = 'boolean'
        m['predicate'] = dict(modality='narrative', source_families=['news'],
                             semantic_condition='A disclosed milestone is present.')
    return dict(measurement=m, evidence_refs=refs,
                falsifiers=[dict(condition='Unsupported in cited observation.',
                                 expected_observation='Unavailable.')])


def old_rows(c, candidate):
    return SignalEvolutionEngine._controller_evidence_excerpts(
        candidate, {**c._facts, **c._events})


def state(c):
    return dict(ledger=[e.to_dict() for e in c.ledger.entries],
                read_progress=list(c._read_progress.values()),
                last_action_result=c._last_action_result)


def main():
    source = REPO / 'runs/diagnostics/reviewed_gpre_capture_snapshot_20261021_v1/stage/snapshot/documents/1179.json'
    document = RawInfoDocument.from_dict(json.loads(source.read_text()))
    facts = project_facts_from_documents([document], case_ref='case-001')
    fact = next(f for f in facts if f.concept == 'EntityCommonStockSharesOutstanding')
    row = SignalEvolutionEngine._controller_evidence_excerpts(
        proposal([fact.fact_ref]), {fact.fact_ref: fact})[0]
    assert len(fact.exact_span) == 692
    assert len(row['exact_span']) == 600
    assert fact.exact_span in document.content
    actual = dict(source_path=str(source.relative_to(REPO)),
        source_file_sha256=hashlib.sha256(source.read_bytes()).hexdigest(),
        document_id=document.document_id, content_hash=document.content_hash,
        fact=asdict(fact), old_row=row,
        omitted_suffix=fact.exact_span[600:],
        evidence_kind='actual_saved_source; synthetic case binding; direct old helper')
    (ROOT/'actual-1179-whole-fact.json').write_text(json.dumps(actual, indent=2)+'\n')

    wide = list(facts)[:13]
    wide_rows = SignalEvolutionEngine._controller_evidence_excerpts(
        proposal([f.fact_ref for f in wide]), {f.fact_ref:f for f in wide})
    assert len(wide_rows) == 12
    controls = {'real_source_13_whole_facts':dict(refs=[f.fact_ref for f in wide],
        old_rows=wide_rows, expected_count=13, observed_count=len(wide_rows))}

    body = 'Public front matter. ' * 80 + 'TAIL_MILESTONE: testing reached the final stage. ' + 'Later unread details. '*50
    doc = RawInfoDocument.create(document_id='synthetic-narrative',
        company_id='synthetic-company', source_type='company_news',
        published_at=NOW, available_at=NOW, content=body,
        metadata={'private_unread_metadata':'DO_NOT_DISCLOSE_METADATA'})
    offset = body.index('TAIL_MILESTONE')
    docref = 'document-' + doc.document_id
    for target in ['document_ref', 'event_ref']:
        c = controller([doc])
        action(c, 'fetch_evidence', case_refs=['case-001'],
               source_families=['news'], max_documents=1)
        eventref = next(iter(c._events))
        ref = docref if target == 'document_ref' else eventref
        before = proposal([ref], narrative=True)
        unread_rejected = None
        try:
            action(c, 'propose_candidate', candidate=before)
        except Exception as exc:
            unread_rejected = str(exc)
        assert unread_rejected  # available narrative must first be read
        action(c, 'read_span', **{target: ref}, offset=offset, length=47)
        read_state = state(c)
        assert 'TAIL_MILESTONE' in c._last_action_result['masked']
        action(c, 'inspect_catalog', scope='signals')
        status, candidates, _ = action(c, 'propose_candidate', candidate=before)
        assert status == 'candidate'
        rows = old_rows(c, before)
        assert 'TAIL_MILESTONE' not in json.dumps(rows)
        controls[target+'_tail'] = dict(candidate=before, native_accepted=True,
            unread_rejected=unread_rejected, old_rows=rows,
            read_state=read_state, final_state=state(c),
            expected_read_text=body[offset:offset+47], raw_content_hash=doc.content_hash)

    # Shared immutable document: event-only read belongs only to its selected
    # case; document read legitimately exposes all fetched case bindings.
    c = controller([doc], [case(doc.company_id,'one'), case(doc.company_id,'two')])
    action(c,'fetch_evidence',case_refs=['case-001','case-002'],source_families=['news'],max_documents=1)
    event = next(e for e in c._events.values() if e.case_ref == 'case-001')
    action(c,'read_span',event_ref=event.event_ref,offset=offset,length=47)
    one = dict(c._last_action_result)
    action(c,'read_span',document_ref=docref,offset=offset,length=47)
    both = dict(c._last_action_result)
    controls['same_document_case_scope'] = dict(event_read=one, document_read=both,
        merged_progress=state(c)['read_progress'])
    assert one['case_refs'] == ['case-001'] and both['case_refs'] == ['case-001','case-002']

    # Actual source native fetch also generates relation refs. Use a relation
    # alone with a neutral observable: the proposal validator admits it without
    # named-concept claims, yet old engine harvest produces no evidence rows.
    c = controller([document])
    action(c,'fetch_evidence',case_refs=['case-001'],source_families=['financial'],max_documents=1)
    relation = next(iter(c._relations.values()))
    candidate = proposal([relation.relation_ref])
    status, _, _ = action(c,'propose_candidate',candidate=candidate)
    assert status == 'candidate' and old_rows(c,candidate) == []
    controls['actual_source_relation_only'] = dict(candidate=candidate,
        native_accepted=True, relation=asdict(relation),
        operands=[asdict(c._facts[ref]) for ref in relation.fact_refs],
        old_rows=[], final_state=state(c))

    # Unknown ref must fail before handing to a materializer, even if a caller
    # bypasses the ordinary controller proposal validator.
    controls['predeclared_postrepair_controls'] = [
        'unknown reference fails closed before materialization',
        'unread document ref never exports body or private metadata',
        'only actual read ranges export; later unread tail stays absent',
        'event range remains scoped after same-range document read merges progress',
        'relation includes ordered complete operand facts and source/hash/PIT bindings',
        'all cited rows preserved beyond twelve; whole JSON fact remains parseable',
        'masked native spec, skill, tests payloads preserve source lineage and remove identity',
        'oversized complete handoff respects actual existing request budget before dispatch',
        'legacy object-based excerpt helper retains supported fact/event callers',
    ]
    (ROOT/'before-controls.json').write_text(json.dumps(controls,indent=2)+'\n')
    manifest={name:hashlib.sha256((ROOT/name).read_bytes()).hexdigest() for name in (
        'before-signal_evolution.py.txt','before-mining_controller.py.txt',
        'freeze_controls.py','actual-1179-whole-fact.json','before-controls.json')}
    (ROOT/'before-manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
    print(json.dumps(dict(actual_span_chars=len(fact.exact_span), old_span_chars=len(row['exact_span']),
        native_reachable_losses=['document_tail','event_tail','relation_only'],
        thirteen_rows_observed=len(wide_rows), network_calls=0, model_calls=0)))


if __name__ == '__main__':
    main()
