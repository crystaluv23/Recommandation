"""Historical first-draft construction; final oracle has explicit preauthor revision2.

Do not rerun to replace the frozen final oracle; this script refuses overwrite.
Parent prospective clarification and final obligations are in acceptance-obligations.json.
"""
from __future__ import annotations
import datetime
import hashlib
import json
from pathlib import Path

ROOT = Path('/Users/l/Project/Recommandation')
OUT = ROOT / 'runs/diagnostics/icfr_native_capability_20261023_v1/oracle'


def binding(path):
    """Identify the exact local evidence/contract observed for this freeze."""
    path = Path(path)
    return {'path': str(path), 'sha256': hashlib.sha256(path.read_bytes()).hexdigest()}


def load(path):
    """Read a local source or contract inventory without invoking any service."""
    return json.loads(Path(path).read_text())


def main():
    """Write a non-overwriting prospective oracle with source facts, not candidate answers."""
    dest = OUT / 'acceptance-obligations.json'
    if dest.exists():
        raise RuntimeError('Frozen oracle exists; refusing overwrite or post-result relaxation')
    evidence_path = ROOT / 'runs/diagnostics/icfr_native_capability_20261023_v1/source-review/bindings-evidence.json'
    evidence = load(evidence_path)
    material_path = ROOT / 'runs/diagnostics/mining_capability_frontier_20261023_v1/independent/narrative-material-bindings.json'
    material = load(material_path)
    definition_path = ROOT / 'runs/diagnostics/mining_capability_frontier_20261023_v1/independent/function-and-definition-map.json'
    definitions = load(definition_path)
    stable = []
    for r in definitions['stable_registry18']:
        if r['spec'].get('modality') != 'narrative':
            continue
        spec_path = Path(r['source']['path'])
        spec = load(spec_path)
        skill_path = Path(r['materialized_skill']['path'])
        stable.append({'exact_ref': r['signal_ref'], 'spec': binding(spec_path),
                       'definition': spec['definition'], 'skill': binding(skill_path),
                       'skill_text': skill_path.read_text()})
    assert len(stable) == 6
    facts = {
        'case-005': {'object': 'Management conclusion about ICFR control environment for accounting/presentation of complex financial instruments; explicitly not effective due to a material weakness, and unremediated during this report period.',
                     'assessment_scope': {'report_period_end': '2025-03-31', 'direct_date_scope': 'Disclosure-controls evaluation is as of quarter end March 31, 2025; the same paragraph says management ICFR conclusion during the period covered. Do not strengthen this wording into a separate newly dated later assessment.'},
                     'mandatory_distinctions': ['Actual identified ICFR weakness, not merely may/could risk.', 'Remediation intent and financing dependence do not prove remediation completed.', 'Keep disclosure controls and ICFR distinct even though they appear in one paragraph.'],
                     'unknown_rules': 'No inference about the latest cutoff-day state, actual later remediation, or stock-outcome effect. Adequate exact paragraph must not become globally unknown merely because independent effect is unverified.'},
        'case-006': {'object': 'Management/Company ICFR effectiveness assessment explicitly says there were no control deficiencies constituting material weaknesses.',
                     'assessment_scope': {'explicit_assessment_date': '2024-12-31', 'report_period_end': '2024-12-31'},
                     'mandatory_distinctions': ['Explicit dated contrary conclusion is stronger than silence.', 'Same filing hypothetical future weaknesses do not override actual dated assessment.', 'No broad claim of no deficiencies, no risk, or effective controls in all respects beyond exact statement.'],
                     'unknown_rules': 'Later/current condition and predictive effect remain unknown; explicit source conclusion at its assessment date cannot be discarded to make this a missing-data case.'},
        'case-003': {'object': 'Hypothetical may-experience-material-weakness risk language; management ICFR assessment expressly omitted under newly public company transition period.',
                     'assessment_scope': {'report_period_end': '2024-12-31', 'management_icfr_assessment_date': None, 'reason': 'No management assessment is supplied; report period is not an assessment date.'},
                     'mandatory_distinctions': ['Hypothetical risk is not actual identification.', 'Explicit no-assessment is not an explicit no-material-weakness conclusion.', 'Do not substitute disclosure-controls assessment or no-change language for missing management ICFR assessment.'],
                     'unknown_rules': 'A source-grounded domain unknown/insufficient-management-assessment conclusion is correct; a technical/budget failure is not this domain result.'},
        'case-001': {'object': 'Original Critical Metals filing calls six items significant deficiencies, defines that concept as less severe than material weakness, then Item15 labels identified items material weaknesses.',
                     'assessment_scope': {'report_period_end': '2024-06-30', 'explicit_references': ['2024-06-30', '2023-06-30'], 'direct_date_scope': 'Audit/ICFR statements reference FY2024 and FY2023; retain the exact sentence scope rather than inventing a later cutoff assessment.'},
                     'mandatory_distinctions': ['Significant deficiency differs from material weakness.', 'Internal terminology conflict is real original-body content; preserve both sides.', 'No lexical tie-break, majority vote, severity upgrade, or silent choice of the favorable sentence.'],
                     'unknown_rules': 'A preserved conflict/unknown about clean severity classification is correct. Neutral, absence, or definite material weakness inferred by deleting one side fails.'}}
    cases = []
    for ref in ['case-001', 'case-003', 'case-005', 'case-006']:
        src = next(r for r in evidence['source_results'] if r['case_ref'] == ref)
        cited = [a for a in src['anchors'] if a['kind'] in
                 ['actual_management_icfr_conclusion', 'explicit_nonremediation',
                  'explicit_no_material_weakness_conclusion', 'hypothetical_only_counterexample',
                  'terminology_conflict_counterexample', 'additional_management_or_clock_countercheck']]
        for a in cited:
            assert hashlib.sha256(a['raw_span'].encode()).hexdigest() == a['raw_span_sha256']
        cases.append({'case_ref': ref, 'case_id': src['case_id'], 'source_number': src['source_number'],
                      'cutoff': src['cutoff'], 'source': src['source'], 'original': src['original'],
                      'document_id': src['source_metadata']['document_id'],
                      'content_hash': src['source_metadata']['content_hash'],
                      'source_url': src['source_url'], 'registrant_cik': src['submissions_issuer']['cik'],
                      'accession': src['exact_submission_row']['accessionNumber'],
                      'form': src['exact_submission_row']['form'],
                      'acceptance_at': src['exact_submission_row']['acceptanceDateTime'],
                      'published_at': src['source_metadata']['published_at'],
                      'available_at': src['source_metadata']['available_at'],
                      'raw_evidence_anchors': cited, **facts[ref]})
    oracle = {
        'schema_version': 'private-prospective-icfr-native-acceptance-v1',
        'frozen_at_utc': datetime.datetime.now(datetime.timezone.utc).isoformat(),
        'privacy': 'Private evaluator-only obligations. Never supply this file, oracle passages, expected mapping, source locators or private source classifications to authors.',
        'prospective_boundary': {'author_outputs_read': False, 'candidate_json_supplied': False,
                                 'fixed_candidate_enum_answers': False, 'output_rule': 'Derive concrete expected output independently from the candidate own immutable definition after authoring and before consumer results. This rule and original facts cannot be relaxed after results. A candidate outside this scope is rejected, not used to rewrite oracle.'},
        'contract_bindings': [binding(ROOT / p) for p in [
            'spec/scripts/run_icfr_native_capability_stage.md', 'spec/vision.md', 'spec/architecture.md',
            'spec/engineering-mvp.md', 'spec/src/stock_opportunity_agent/research/evolution_signal_roles.md',
            'spec/src/stock_opportunity_agent/signal_library.md']],
        'source_review': binding(evidence_path), 'source_material': binding(material_path),
        'source_scope': {'level': 'bounded local historical filing-source binding',
                         'not_claimed': ['contemporaneous remote attestation', 'acceptance-instant exact historical bytes',
                                         'independent no-modification version history', 'latest cutoff-day ICFR truth'],
                         'availability_rule': 'SEC retained exact submission acceptance establishes the local historical filing clock; 2026 retrieved_at is capture time. Neither timestamp field alone nor hashes alone prove source authenticity; use bound original body/request/issuer/period/cache chain.'},
        'research_semantics': {'axis': 'existing fixed surge direction; never redefine SignalValue as generic predicate presence',
                               'target': 'Existing fixed adjusted-share-price surge outcome; no label, horizon, class or direction redefinition.',
                               'rules': ['Separate source factual state, candidate measurement state and hypothesized research orientation.',
                                         'Do not equate actual weakness with positive just because predicate is present, or no weakness with negative just because absent.',
                                         'Require candidate own pre-result definition and rationale to state applicable state meaning, research relevance, counterevidence and uncertainty.',
                                         'A defensible target-relevant hypothesis need not prove independent predictive benefit, but stock direction/magnitude cannot be fabricated from the source.',
                                         'Unverified effect must remain unverified; technical admission and diagnostic use never establish empirical orientation.',
                                         'If source facts are measurable but direction is not justified, preserve factual distinctions and uncertainty under existing contracts; do not invent a mapping to meet this control.',
                                         'An irreconcilable direction/definition contract fails or stays unknown before promotion; do not silently change canonical schema.']},
        'novelty_baseline': {'six_exact_existing_narrative_definitions': stable,
                             'finding': 'None measures dated management ICFR assessment/material-weakness/remediation conclusions. This is a distinct business object from capital/listing action, changed guidance, qualifying orders/order quality, commercialization, customer concentration. Negative-word substring count is not equivalent semantic measurement.',
                             'candidate_review': 'Object-level novelty remains to be checked against actual generated definition; renaming, parameter-only repackaging, generic risk/keyword presence or duplicated existing measurement fails.'},
        'fixed_denominators': {'pipeline_positive_control': 1, 'consumer_source_controls': 4,
                               'consumer_case_refs': ['case-001', 'case-003', 'case-005', 'case-006'],
                               'retention': 'Keep every failed, skipped, blocked, unknown or unselected member in its frozen denominator. No at-least-one-success subset reporting.'},
        'pipeline_positive_control': {
            'pass_requires_all': ['Fresh independent native Mining actually authors a new reusable source-grounded ICFR measurement from authorized material; no handwritten or oracle-derived Signal substitute.',
                                  'Preserve original dev8 grouping/axis, all existing backlog/context obligations, authentic role requests/answers/corrections/ledgers and native materialization evidence.',
                                  'Definition covers the answerable ICFR material family and expressly handles actual weakness, explicit contrary conclusion, missing/omitted assessment and terminology conflict; it may choose a legitimate reusable formulation, not a company/date-only lookup or arbitrary exclusion of controls.',
                                  'An author cannot make the positive control vacuous by choosing impossible inputs, a post-cutoff comparison, an arbitrary narrow subfamily excluding available contrary facts, or all-cases unavailable.',
                                  'Native spec→skill→tests→real fixture execution faithfully implements the authored definition; fixture answers do not alter definition or authorize new source policy.',
                                  'Independent source/semantic review binds exact candidate/spec/skill/tests/oracle hashes before any promotion, and rejects unknown or incorrect semantics.',
                                  'Actual native technical validation, duplicate checks, admission/provenance recording and atomic promotion publish an exact version with predictive effect unverified; no fabricated passing validation or effectiveness evaluator.',
                                  'Baseline18 remain unchanged; reopened Registry retains exact promoted spec/skill/tests/admission/transition.',
                                  'All four actual native Fast source controls autonomously retrieve and execute the newly admitted exact version within portfolio bounds; result passes source review and reaches actual Reflect/final context with diagnostic-use binding.',
                                  'Durable reopen equality and terminal seal preserve accepted outputs and failure denominator without business pointers/committed-use events.'],
            'fails': ['Honest no-pattern/insufficient-evidence outcome (legal domain outcome, but fails this answerable full-chain positive control).',
                      'Budget/resource/transport/identity/schema/authoring failure, unselected new version, skipped execution or incomplete consumer chain.',
                      'Handwritten candidate, hand-authored answer, forced new-ref retrieval, oracle leak, reentry of completed phases, or retroactive oracle weakening.',
                      'Any known critical source/semantic/version/admission/consumer error accepted as passing.']},
        'consumer_controls': {'original_source_obligations': cases,
                              'per_case_pass_requires_all': ['Execute the exact new admitted version through autonomous native retrieval and production portfolio limits; record any omissions and unresolved need.',
                                                             'Independently derive expected output from frozen candidate definition and original facts, preserving object, report/assessment date, cutoff and source provenance.',
                                                             'Exact source-grounded result and interpretation distinguish actual/contrary/omitted/conflicting evidence; source uncertainty and effect uncertainty remain separate.',
                                                             'Reflect closes only proven parts of the dated public-assessment need; missing assessment/conflict/current-state residuals remain explicit.',
                                                             'Final context preserves actual result, coverage/cause, evidence, period, exact version and residual. Runtime failure may not masquerade as domain unknown.',
                                                             'Save exact diagnostic-use provenance; never record committed round use or stock efficacy.'],
                              'unknown_is_correct_only_when': 'The original source or the frozen measurement truly lacks a clean applicable conclusion, as with omitted management assessment or unresolved terminology conflict; all needed source facts and cause remain visible. Unknown is not blanket permission to evade answerable actual/explicit-contrary cases.',
                              'not_fixed': 'No four-case SignalValue enum mapping or candidate implementation is preauthored. Case facts are private oracle evidence, not production answers.'},
        'counterexample_rejection_rules': ['A keyword hit in source1501 yields definite actual weakness: fail.',
                                          'Source1501 no assessment becomes no weaknesses/favorable fact: fail.',
                                          'Source1500 hypothetical risk overrides explicit dated no-weakness conclusion: fail.',
                                          'Source1768 only one side of conflicting severity terminology is cited/retained: fail.',
                                          'Source1507 remediation plan is treated as completed remediation, or disclosure controls substituted for ICFR: fail.',
                                          'Assessment/report date is promoted to cutoff/current state or retrieved_at to publication date: fail.',
                                          'Technically unavailable-shaped output closes missing-assessment/conflict need as answered domain evidence: fail.',
                                          'Source1507 and1500 collapse to generic presence without preserving their opposite dated factual conclusions: fail.',
                                          'Existing Signal renamed as ICFR, generic risk count, authored fixtures alone, or schema/model agreement treated as new capability: fail.'],
        'stage_spec_review': {'material_conflict_found': False,
                              'interpretations_required': ['Pipeline denominator1 is a capability control, not a candidate quota; honest no-pattern is legal and still control failure.',
                                                           'Private source facts stay out of authors; only preflighted scope-only ICFR assignment may enter.',
                                                           'An existing narrative skill presence-based historical classification does not override this stage explicit surge-axis meaning.',
                                                           'Need formulation and consumer expectations cannot silently add a new global SignalValue definition or canonical interface.']},
        'scope_limits': {'external_calls': 0, 'new_business_labels_check_lockedtest': 0,
                         'business_stage_or_product_changes': 0,
                         'not_closed_by_this_stage': ['magnitude Mining/admission/reuse', 'S1/S2 fresh feedback capability',
                                                      'committed S8 use', 'full business-loop recovery', 'independent benefit', 'whole engineering MVP']}}
    dest.write_text(json.dumps(oracle, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps({'oracle': str(dest), 'binding': binding(dest), 'pipeline_denominator': 1, 'consumer_denominator': 4}))

if __name__ == '__main__':
    main()
