"""Unsupported unavailable-topic findings and independently accepted exact claims."""
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from unittest import TestCase
from unittest.mock import patch

from stock_opportunity_agent.models import StructuredValidationError
from stock_opportunity_agent.research.evolution_core import ResearchEvidenceRef
from stock_opportunity_agent.research.evolution_research_validation import (
    _validate_research_state_refs, _unavailable_signal_state_errors, _signal_batch_model_view,
)
from stock_opportunity_agent.signal_library import (
    NumericMeasurement, SignalBatchResult, SignalEvidence, SignalResult, SignalValue,
)
from tests import test_unavailable_finding_repair as support


NOW = datetime(2025, 9, 30, tzinfo=timezone.utc)
CONTEXT = {'prediction_time': NOW.isoformat()}
CLAIM = 'Customer concentration was not high in the reported period.'


class UnavailableTopicGroundingTests(TestCase):
    def setUp(self):
        self.fixture = support.UnavailableFindingRepairTests()

    def state(self, text, *, refs=(), prior=None):
        prior = prior or self.fixture.prior()
        return replace(prior, current_beliefs=prior.current_beliefs+(text,),
                       supporting_evidence=prior.supporting_evidence+tuple(refs))

    def validate(self, state, *, prior=None, batch=None):
        return _validate_research_state_refs(state, phase='reflect',
            previous_state=prior or self.fixture.prior(), batch=batch or self.fixture.batch(),
            need_dispositions=[], evaluation_context=CONTEXT)

    def source(self, claim=CLAIM, *, raw=None, timestamp=NOW-timedelta(days=1), numeric=False):
        source = SignalResult(signal_id='customer_concentration',version=2,
            value=SignalValue.NEUTRAL,confidence=.5,interpretation=claim,
            supporting_evidence=(SignalEvidence('offline-source',raw or claim,timestamp),),
            measurement=NumericMeasurement(.25,'ratio','part / total','2025-06-30') if numeric else None)
        ref = ResearchEvidenceRef(kind='signal',signal_ref=source.ref,
            evidence_group='supporting',evidence_index=0,claim=claim)
        batch = self.fixture.batch()
        return ref,SignalBatchResult(batch.results+(source,),signal_calls=3)

    def test_no_matching_unavailable_finding_never_projects_independent_sources(self):
        prior = self.fixture.prior()
        batch = self.fixture.batch()
        available_only = SignalBatchResult((batch.results[1],), signal_calls=1)
        cases = (
            (self.state('Customer concentration is weak.'), available_only),
            (self.state('An unrelated business fact remains unchanged.'), batch),
            (prior, batch),
        )
        # A projection tripwire proves the adjacent validator path is a no-op,
        # rather than teaching production evidence validation a stub schema.
        with patch('stock_opportunity_agent.research.evolution_research_validation.'
                   '_independent_unavailable_topic_claims',
                   side_effect=AssertionError('unrelated evidence projected')) as projection:
            for state, source_batch in cases:
                self.assertEqual(_unavailable_signal_state_errors(
                    prior, state, source_batch, evaluation_context=CONTEXT), [])
            projection.assert_not_called()

    def test_marker_blind_qualitative_findings_are_rejected_then_atomically_removed(self):
        for text in ('Customer concentration is weak.', 'Customer concentration is strong.',
                     'Customer concentration deteriorated.', 'Customer concentration is absent.',
                     'Customer concentration is unknown, but customer concentration is weak.',
                     'Customer concentration remains unknown. Customer concentration is weak.'):
            with self.subTest(text=text):
                state = self.state(text)
                with self.assertRaises(StructuredValidationError) as caught:self.validate(state)
                finding = [i for i in caught.exception.issues if i.code=='unavailable_signal_treated_as_finding']
                self.assertEqual(len(finding),1)
                self.assertEqual(finding[0].allowed_repairs,('remove',))
                step,caller=self.fixture.reflect(state.to_dict())
                self.assertEqual(step.value,self.fixture.prior());self.assertEqual(len(caller.calls),1)

    def test_unrelated_negation_does_not_exempt_another_topic_or_split_a_member(self):
        text='Customer concentration is unknown; cash runway is weak, despite no announced financing change.'
        batch=self.fixture.batch()
        batch=SignalBatchResult(batch.results+(replace(batch.results[0],signal_id='cash_runway'),),signal_calls=3)
        errors=_unavailable_signal_state_errors(self.fixture.prior(),self.state(text),batch,evaluation_context=CONTEXT)
        self.assertEqual({row['signal_ref'] for row in errors},{'customer_concentration:v1','cash_runway:v1'})
        self.assertEqual({row['text'] for row in errors},{text})
        # Explicit denial of economic absence remains wrong belief placement.
        raw69=('Historical share retirement, revolver availability and covenant compliance provide capital-structure context; '
            'they do not establish prospective net dilution or a directional financing catalyst. '
            'The admitted financing measurement has unverified predictive effect. '
            'Insufficient visible evidence for operating cash flow margin leaves self-funding capacity unresolved; '
            'this domain coverage outcome is not a technical failure or evidence of economic absence.')
        self.assertEqual(len(raw69),453)
        unavailable=replace(self.fixture.batch().results[0],signal_id='operating_cash_flow_margin')
        batch=SignalBatchResult((unavailable,self.fixture.batch().results[1]),signal_calls=2)
        errors=_unavailable_signal_state_errors(self.fixture.prior(),self.state(raw69),batch,evaluation_context=CONTEXT)
        self.assertEqual([e['text'] for e in errors],[raw69])

    def test_current_available_exact_raw_readable_and_normalized_reference_prove_independence(self):
        for raw in (CLAIM, 'Customer <b>concentration</b> was not high in the reported period.'):
            ref,batch=self.source(raw=raw)
            state=self.state(CLAIM,refs=(ref,))
            self.assertEqual(self.validate(state,batch=batch).current_beliefs,state.current_beliefs)
            # The owning validator's existing unversioned-ref normalization is
            # allowed only when that Signal ID has one current matching result.
            other=replace(batch.results[-1],signal_id='customer_concentration_report')
            ref=replace(ref,signal_ref='customer_concentration_report')
            adjusted=SignalBatchResult(batch.results[:2]+(other,),signal_calls=3)
            accepted=self.validate(self.state(CLAIM,refs=(ref,)),batch=adjusted)
            self.assertEqual(accepted.supporting_evidence[-1].signal_ref,other.ref)
        ref,batch=self.source();state=self.state(CLAIM,refs=(ref,))
        for context in (None,{'prediction_time':'2025-09-30T00:00:00'}):
            self.assertTrue(_unavailable_signal_state_errors(self.fixture.prior(),state,batch,evaluation_context=context))
        offset={'prediction_time':NOW.astimezone(timezone(timedelta(hours=9))).isoformat()}
        self.assertEqual(_unavailable_signal_state_errors(self.fixture.prior(),state,batch,evaluation_context=offset),[])

    def test_prior_exact_claim_and_provenance_survive_but_changed_claim_does_not(self):
        for ref in (ResearchEvidenceRef(kind='basic_info',projection_id='prior-concentration',
                        exact_text=CLAIM,claim=CLAIM),
                    ResearchEvidenceRef(kind='signal',signal_ref='old_report:v1',
                        evidence_group='counter',evidence_index=0,claim=CLAIM)):
            prior=replace(self.fixture.prior(),supporting_evidence=self.fixture.prior().supporting_evidence+(ref,))
            state=self.state(CLAIM,prior=prior)
            self.assertEqual(self.validate(state,prior=prior).current_beliefs,state.current_beliefs)
            changed=replace(ref,claim='Customer concentration was not low in the reported period.')
            state=replace(state,current_beliefs=state.current_beliefs[:-1]+(changed.claim,),
                          supporting_evidence=state.supporting_evidence[:-1]+(changed,))
            with self.assertRaises(StructuredValidationError) as caught:self.validate(state,prior=prior)
            self.assertIn('unavailable_signal_treated_as_finding',{i.code for i in caught.exception.issues})

    def test_ref_membership_wrong_tuple_paraphrase_substring_or_future_is_not_grounding(self):
        ref,batch=self.source()
        variants=[(replace(ref,signal_ref='missing_report:v1'),batch),
                  (replace(ref,evidence_group='counter'),batch), (replace(ref,evidence_index=99),batch),
                  (replace(ref,claim=CLAIM[:-1]),batch),
                  (replace(ref,claim='Customer concentration appears not high in the reported period.'),batch)]
        variants.append(self.source(timestamp=NOW+timedelta(seconds=1)))
        ref,long_batch=self.source(raw=CLAIM+' Original narrative continues.'*100)
        compact=_signal_batch_model_view(long_batch)[-1]['evidence']['supporting'][0]['model_evidence_text']
        self.assertIn('[bounded evidence text omitted]',compact)
        variants.append((replace(ref,claim=compact),long_batch))
        for candidate,source_batch in variants:
            with self.subTest(ref=candidate):
                state=self.state(candidate.claim,refs=(candidate,))
                with self.assertRaises(StructuredValidationError) as caught:self.validate(state,batch=source_batch)
                self.assertIn('unavailable_signal_treated_as_finding',{i.code for i in caught.exception.issues})
        # Very small remaining display budgets emit a prefix without a marker;
        # that prefix is still not the complete normalized source literal.
        with patch('stock_opportunity_agent.research.evolution_research_validation.MAX_REFLECT_SIGNAL_BATCH_EVIDENCE_CHARS',30):
            prefix=_signal_batch_model_view(long_batch)[-1]['evidence']['supporting'][0]['model_evidence_text']
            self.assertNotIn('[bounded evidence text omitted]',prefix)
            with self.assertRaises(StructuredValidationError) as caught:
                self.validate(self.state(prefix,refs=(replace(ref,claim=prefix),)),batch=long_batch)
            self.assertIn('unavailable_signal_treated_as_finding',{i.code for i in caught.exception.issues})

    def test_producer_canonical_numeric_claim_is_exact_not_free_prose(self):
        claim='customer_concentration=0.25'
        ref,batch=self.source(claim,raw='{"part":25,"total":100}',numeric=True)
        state=self.state(claim,refs=(ref,))
        self.assertEqual(self.validate(state,batch=batch).current_beliefs,state.current_beliefs)
        altered=replace(ref,claim='Customer concentration is 0.25 and looks weak.')
        with self.assertRaises(StructuredValidationError) as caught:
            self.validate(self.state(altered.claim,refs=(altered,)),batch=batch)
        self.assertIn('unavailable_signal_treated_as_finding',{i.code for i in caught.exception.issues})

    def test_zero_percent_still_has_quantity_gate_and_questions_remain_questions(self):
        with self.assertRaises(StructuredValidationError) as caught:
            self.validate(self.state('Customer concentration is 0%.'))
        self.assertIn('assertion_without_support',{i.code for i in caught.exception.issues})
        prior=self.fixture.prior()
        state=replace(prior,open_questions=('Why is customer concentration still unknown?',),
            next_information_needs=prior.next_information_needs+('What source can establish customer concentration?',))
        self.assertEqual(self.validate(state).to_dict(),state.to_dict())
        # Whole-word topic requirements are retained, without a new stemmer.
        state=self.state('Customer concentrationary evidence is unavailable.')
        self.assertEqual(_unavailable_signal_state_errors(prior,state,self.fixture.batch()),[])
