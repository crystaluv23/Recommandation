"""Research, routing, prediction, and Plan model-role adapters."""

from __future__ import annotations

from stock_opportunity_agent.research.basic_info_orientation import orientation_menu, validate_raw_orientation_policy

import contextlib
import json
import re
from copy import deepcopy
from dataclasses import replace
from datetime import date, datetime, timezone
from typing import Any, Callable, Iterable, Mapping
from stock_opportunity_agent.research.basic_info_visibility import basic_info_source_index, pack_critic_visibility
from stock_opportunity_agent.artifacts import canonical_json_hash as _canonical_hash
from stock_opportunity_agent.research.evolution_dataset import _add_months
from stock_opportunity_agent.research.evolution_reflection_memory import (
    ReflectionMemoryIndex,
    ReflectionValidationError,
    reflection_fact_inference_fields,
    violates_opportunity_proof_gate,
)
from stock_opportunity_agent.research.evolution_state_patch import (
    PATCH_INSTRUCTION,
    apply_state_patch,
    state_patch_contract,
)
from stock_opportunity_agent.llm.agent import AgentUsage
from stock_opportunity_agent.models import (
    StructuredValidationError,
    ValidationError,
    ValidationIssue,
)
from stock_opportunity_agent.research.scheme_evolution import (
    AgentStep,
    BlindPrediction,
    CandidateExecutionRejected,
    CandidateProposalRejected,
    CaseReflectionEvidence,
    GroundTruth,
    InformationPlan,
    PlanMetrics,
    PlanMetaReflection,
    PlanRecord,
    PlanReflection,
    PredictionSelfReflection,
    ResearchState,
    ResearchDecision,
    ResearchEvidenceRef,
    RoundMetaEntry,
    RuntimeBudgetExceeded,
    runtime_termination_view,
    SignalSelectionDecision,
    candidate_judgment_feedback,
    is_technical_exclusion_trajectory,
    jev_decision_feedback,
    magnitude_feedback,
    research_jev_calibration_diagnostics,
    research_magnitude_diagnostics,
    technical_completion_diagnostics,
    _mask_identity_values,
)
from stock_opportunity_agent.signal_library import (
    FrozenSignalRegistry,
    SignalBatchResult,
    SignalCoverage,
    SignalValue,
    SignalResult,
    SignalSpec,
    SIGNAL_CONTEXT_TAGS,
    SIGNAL_EXECUTION_STATUS_INSTRUCTION,
    signal_result_model_view,
    signal_measurement_scope,
    require_signal_result_pit,
    _thaw_json,
)
from stock_opportunity_agent.research.evolution_settings import (
    REGISTERED_SOURCE_TYPE_CATALOG,
    ROLE_OUTPUT_TOKEN_LIMITS,
)
from stock_opportunity_agent.research.evolution_transport import (
    ExternalBudgetExhausted,
    JSONRoleCaller,
    _complete_json_with_invalid_value,
    _normalize_field,
    _scan_payload,
)
from stock_opportunity_agent.research.evolution_output_validation import (
    _BLIND_PREDICTION_OUTPUT,
    _INFORMATION_PLAN_OUTPUT,
    _RESEARCH_STATE_CORRECTION_GUIDANCE,
    _RESEARCH_STATE_OUTPUT,
    _UNTRUSTED_DATA_INSTRUCTION,
    _SOURCE_FACT_RELATION_INSTRUCTION,
    _blind_prediction_with_baseline,
    _price_reasoning_issues,
    _measurement_reasoning_issues,
    _computed_period_issues,
    _COMPUTED_PERIOD_INSTRUCTION,
    _PRICE_SHORTFALL_INSTRUCTION,
    _realized_outcome_issues,
    _REALIZED_OUTCOME_INSTRUCTION,
    _context_signal_results,
    _compact_posthoc_context,
    _require_context_signal_pit,
    _INCREMENTAL_ROLE_INSTRUCTION,
    _emit_runtime_progress,
    _market_data_absence_paths,
    _complete_parsed_role,
    _routing_context_only_fallback,
    _parse_role_output,
    _research_state_evidence_grounding_fallback,
    _scoped_correction_drift_paths,
    _validate_plan_for_proposer_context,
    _validate_proposal_change_focus,
    _validation_obligations,
)
from stock_opportunity_agent.research.evolution_research_validation import (
    _INHERITABLE_EXPECTATION_CONTEXT,
    _SYMBOLIC_AS_OF_BOUND,
    _bounded_residual_need,
    _coordinated_residual_facet_terms,
    _future_source_date_refs,
    _need_as_of_bound_clause,
    _normalize_information_plan_output,
    _normalize_research_state_output,
    _normalized_need_content_tokens,
    _prediction_time_from_context,
    _reflection_need_transition_contract,
    _reflection_selection_intents,
    raw_need_disposition_issues,
    validate_need_dispositions,
    _research_state_capacity,
    _routing_residual_facet_candidates,
    _shared_distinctive_phrase,
    _signal_batch_model_view,
    _signal_evidence_ref_catalog,
    _validate_raw_information_plan_request_fields,
    _validate_research_state_refs,
)


class LLMResearchController:
    """Concrete H_init/H_reflect adapter backed by a guarded JSON role client."""

    def __init__(self, caller: JSONRoleCaller) -> None:
        self.caller = caller
        self.request_token_budget: int | None = None
        self.evaluation_context: dict[str, Any] | None = None
        self.evaluation_anchor: dict[str, Any] | None = None
        self.computed_metrics: list[dict[str, Any]] = []
        self.computed_metric_cards: tuple[Mapping[str, Any], ...] = ()
        self.signal_research_status: dict[str, Mapping[str, Any]] = {}
        self.document_channel: Any = None
        self.reflection_selections: tuple[SignalSelectionDecision, ...] = ()
        self.reflection_must_finalize = False
        self.reflection_termination_trigger: RuntimeStopReason | None = None

    def set_request_token_budget(self, value: int) -> None:
        self.request_token_budget = int(value)

    def set_evaluation_context(self, prediction_time: datetime) -> None:
        """Set the runtime-owned point-in-time horizon for the next H_init call."""

        if (
            prediction_time.tzinfo is None
            or prediction_time.utcoffset() is None
        ):
            raise ValidationError("prediction_time must be timezone-aware")
        normalized = prediction_time.astimezone(timezone.utc)
        self.evaluation_context = {
            "prediction_time": normalized.isoformat(),
            "horizon": "six_calendar_months",
            "horizon_end": _add_months(normalized.date(), 6).isoformat(),
        }
        if self.evaluation_anchor is not None:
            self.evaluation_context["evaluation_anchor"] = dict(
                self.evaluation_anchor
            )

    def set_evaluation_anchor(self, anchor: Mapping[str, Any] | None) -> None:
        """Attach the computed evaluation anchor for verbatim disclosure.

        The anchor block (baseline mean, doubling threshold, recent close and
        derived ratios) is runtime-owned computation. It is disclosed
        verbatim in the H_init/H_reflect payloads and enforced by the state
        validator: the model copies these numbers, never restates or
        recomputes them.
        """

        if anchor is None:
            self.evaluation_anchor = None
            if isinstance(self.evaluation_context, dict):
                self.evaluation_context.pop("evaluation_anchor", None)
            return
        if not isinstance(anchor, Mapping) or anchor.get("status") != "available":
            raise ValidationError(
                "evaluation anchor must be an available computed baseline block"
            )
        self.evaluation_anchor = dict(anchor)
        if isinstance(self.evaluation_context, dict):
            self.evaluation_context["evaluation_anchor"] = dict(anchor)

    def set_computed_metrics(self, cards: list[dict[str, Any]]) -> None:
        """Attach runtime-computed metric cards for verbatim disclosure.

        The model-facing payload receives the readable prose form, not the
        JSON card structure, so computed results are consumed as narrative
        control data rather than miscited as evidence exact_text spans.
        """

        from stock_opportunity_agent.research.compute_tools import (
            format_computed_card_readable,
        )

        self.computed_metric_cards = tuple(deepcopy(card) for card in cards)
        self.computed_metrics = [
            {"readable": format_computed_card_readable(card)}
            for card in cards
        ]

    def set_document_channel(self, provider: Any) -> None:
        """Attach the bounded in-loop Raw Info catalog/fetch channel.

        The provider exposes ``catalog_view(cursor=0)`` (bounded point-in-time
        document cards) and ``fetch(entries)`` (bounded verbatim or
        section views resolved through the disclosure interface). While
        set, every H_reflect call receives the catalog view and may spend
        bounded mid-call exchanges on catalog paging, ``fetch_documents``
        and deterministic computation before
        returning the state — the improvised retrieval channel alongside
        frozen-policy Signal execution.
        """

        self.document_channel = provider

    def set_signal_research_status(self, status: Mapping[str, Mapping[str, Any]]) -> None:
        """Bind status from one frozen Registry; expose only current-batch refs."""

        self.signal_research_status = _thaw_json(status)

    def set_reflection_runtime_context(
        self,
        *,
        selections: tuple[SignalSelectionDecision, ...],
        must_finalize: bool,
        termination_trigger: RuntimeStopReason | None,
    ) -> None:
        """Set one-shot runtime facts for the next H_reflect call."""

        self.reflection_selections = tuple(selections)
        self.reflection_must_finalize = bool(must_finalize)
        self.reflection_termination_trigger = termination_trigger

    def initialize(
        self, plan: InformationPlan, basic_info: Mapping[str, Any]
    ) -> AgentStep[ResearchState]:
        evaluation_context = (
            dict(self.evaluation_context)
            if self.evaluation_context is not None
            else None
        )
        payload: dict[str, Any] = {
            "initial_research_skill": plan.initial_research_skill,
            "basic_info": dict(basic_info),
        }
        if evaluation_context is not None:
            payload["evaluation_context"] = evaluation_context
        if self.evaluation_anchor is not None:
            payload["evaluation_anchor"] = dict(self.evaluation_anchor)
        if self.computed_metrics:
            payload["computed_metrics"] = [
                dict(card) for card in self.computed_metrics
            ]
        state, usage = _complete_parsed_role(
            self.caller,
            stage="research_controller_initialize",
            system_prompt=(
                "Apply H_init to Basic Info only and return one compact ResearchState. "
                "Needs are natural-language issuer evidence questions, never Signal "
                "ids. The fixed six-month adjusted-share-price doubling outcome is the "
                "evaluation definition, not an issuer statement; its baseline date, "
                "or baseline price are runtime inputs, not issuer facts to request. A "
                "future operating event outside the six-month horizon matters only "
                "through within-horizon evidence or milestone that could change "
                "expectations. "
                "When evaluation_anchor is supplied it is deterministic computed "
                "control data retained separately: use it to orient qualitative "
                "judgments and evidence needs, without numerical restatements in "
                "current_beliefs, contradictions or supporting_evidence. Percent changes must keep "
                "their explicit endpoint/target and named denominator consistent: "
                "baseline uses mean_adjusted_close, recent close uses recent_close. "
                "Doubling the baseline is a 100% gain from baseline. Computed metric summaries "
                "in computed_metrics are also control data: use their qualitative "
                "implications for research, but never write them into "
                "current_beliefs, contradictions or supporting_evidence — evidence citations must come "
                "only from basic_info projections. Source catalog dates and filing-form "
                "identifiers are metadata, not literal issuer quotes. Interpret time-bound source wording at its "
                "available_at: an expired event or an old source saying currently "
                "does not establish that the condition remains current at prediction_time. "
                "evaluation_context is control data, not evidence: every need must be "
                "answerable from facts available by prediction_time and must request "
                "evidence that could already exist by prediction_time. You may ask what "
                "was disclosed by then about a scheduled catalyst, but not for contents "
                "or results published later. Every next_information_needs item must "
                "contain only facts absent from visible Basic Info and from the state "
                "you return. Source "
                "status is not projection visibility; partial_context_budget, "
                "omitted_context_budget, visibility_unknown and no_context_spans prove neither presence "
                "nor absence. Source/projection omission flags describe separate budgets; "
                "null means unknown. Omission markers are discovery hints, not evidence. "
                "The final Predictor assembly retains Basic Info "
                "projections, this ResearchState, and later stage products. In "
                "this state retain the smallest material direct support or "
                "counter-evidence without enumerating requests or sources. "
                "Corrections must satisfy every prior obligation simultaneously: a "
                "hypothesis reframed to respect the six-month horizon whose "
                "corrected claims then cite quantities absent from the exact_text "
                "refs is still invalid, and so is the reverse - fixing the claims "
                "by reintroducing an out-of-horizon condition. Re-read every "
                "validation_feedback obligation and keep all previously satisfied "
                "ones satisfied while repairing the named failure."
                + _UNTRUSTED_DATA_INSTRUCTION
                + _SOURCE_FACT_RELATION_INSTRUCTION
                + _COMPUTED_PERIOD_INSTRUCTION
                + _PRICE_SHORTFALL_INSTRUCTION
                + _RESEARCH_STATE_OUTPUT
            ),
            payload=payload,
            parser=lambda value: _validate_research_state_refs(
                ResearchState.from_dict(
                    _normalize_research_state_output(
                        value,
                        initialize=True,
                        basic_info=basic_info,
                        evaluation_context=evaluation_context,
                        control_texts=tuple(card["readable"] for card in self.computed_metrics),
                        computed_metric_cards=self.computed_metric_cards,
                    )
                ),
                phase="initialize",
                basic_info=basic_info,
            ),
            allow_outcomes=False,
            max_output_tokens=ROLE_OUTPUT_TOKEN_LIMITS["controller"],
            max_request_tokens=self.request_token_budget,
            stable_correction_prefix=True,
            correction_guidance=_RESEARCH_STATE_CORRECTION_GUIDANCE,
            enforce_scoped_correction=True,
            exact_compaction_scope=True,
            patch_corrections=True,
            final_validation_fallback=_research_state_evidence_grounding_fallback,
        )
        return AgentStep(state, usage)

    def reflect(
        self,
        plan: InformationPlan,
        state: ResearchState,
        batch: SignalBatchResult,
    ) -> AgentStep[ResearchState]:
        input_cutoff = _prediction_time_from_context(self.evaluation_context)
        if input_cutoff is not None:
            for result in batch.results:
                require_signal_result_pit(result, as_of=input_cutoff)
        selections = self.reflection_selections
        must_finalize = self.reflection_must_finalize
        termination_trigger = self.reflection_termination_trigger
        self.reflection_selections = ()
        self.reflection_must_finalize = False
        self.reflection_termination_trigger = None
        evaluation_context = (
            dict(self.evaluation_context)
            if self.evaluation_context is not None
            else None
        )
        if must_finalize and batch.results and all(
            result.value is SignalValue.UNAVAILABLE
            or result.coverage is SignalCoverage.UNAVAILABLE
            for result in batch.results
        ):
            return AgentStep(
                replace(state, decision=ResearchDecision.FINALIZE), AgentUsage()
            )
        reflect_caller = (
            _DocumentChannelCaller(self.caller, self.document_channel)
            if self.document_channel is not None
            else self.caller
        )
        patch_base = {**state.to_dict(), "need_dispositions": []}
        disposition_metadata: dict[str, Any] | None = None

        def parse_reflected(value: Mapping[str, Any]) -> ResearchState:
            nonlocal disposition_metadata
            disposition_metadata = None
            issues = [
                ValidationIssue(
                    code="research_reflect_envelope_invalid", paths=(name,),
                    message=f"Add required Reflect envelope field {name}",
                    allowed_repairs=("add",),
                ) for name in sorted(set(patch_base) - set(value))
            ] + [
                ValidationIssue(
                    code="research_reflect_envelope_invalid", paths=(name,),
                    message=f"Remove unsupported Reflect envelope field {name}",
                    allowed_repairs=("remove",),
                ) for name in sorted(set(value) - set(patch_base))
            ]
            if issues:
                raise StructuredValidationError(issues)
            try:
                normalized = _normalize_research_state_output(
                    {name: value[name] for name in state.to_dict()},
                    previous_state=state,
                    evaluation_context=evaluation_context,
                    computed_metric_cards=(self.computed_metric_cards + tuple(reflect_caller.computed_metric_cards)
                        if isinstance(reflect_caller, _DocumentChannelCaller) else self.computed_metric_cards),
                )
            except StructuredValidationError as error:
                disposition_issues = raw_need_disposition_issues(
                    value["need_dispositions"], previous_state=state,
                    selections=selections, batch=batch,
                    evaluation_context=evaluation_context,
                )
                raise StructuredValidationError((*error.issues, *disposition_issues)) from error
            reflected_state = _validate_research_state_refs(
                ResearchState.from_dict(normalized),
                phase="reflect",
                previous_state=state,
                batch=batch,
                selections=selections,
                must_finalize=must_finalize,
                evaluation_context=evaluation_context,
                need_dispositions=value["need_dispositions"],
            )
            dispositions = validate_need_dispositions(
                value["need_dispositions"], previous_state=state,
                state=reflected_state, selections=selections, batch=batch,
                evaluation_context=evaluation_context,
            )
            disposition_metadata = {
                "prior_state_hash": _canonical_hash(state.to_dict()),
                "items": [
                    {**row, "prior_need": state.next_information_needs[row["need_index"]]}
                    for row in dispositions
                ],
            }
            return reflected_state

        reflected, usage = _complete_parsed_role(
            reflect_caller,
            stage="research_controller_reflect",
            system_prompt=(
                "Apply H_reflect to the complete Signal batch in logical steps: "
                "signal_research_status describes technical admission and unverified "
                "effect, not proof of contribution. Adopt actual measurement evidence "
                "without claiming that admission establishes prediction benefit. "
                "identify evidence to adopt, update only the affected judgments, "
                "then update answered needs and the continue/finalize decision. "
                "Return only snapshot-bound operations under output_patch_contract. "
                "Runtime assembles and validates the complete Reflect envelope and "
                "preserves all untouched fields. Retained Basic Info provenance "
                "must remain unchanged; only its claim may be restated when needed. "
                "A new Signal evidence ref must use "
                "kind=signal, a signal_ref from the current batch, "
                "evidence_group=supporting or counter, and the zero-based evidence_index. "
                "Use only an exact tuple listed by signal_evidence_ref_catalog. Every "
                "numeric quantity in a new Signal claim must occur in the union of the "
                "model_evidence_text items referenced by refs with that same claim; "
                "runtime revalidates it against complete canonical evidence. Quote "
                "numbers only by copying them from a referenced model_evidence_text: "
                "never include a ratio, monthly average, threshold, or any other value "
                "you computed or recalled from the card description — narrow the claim "
                "to the copied literals instead. "
                "For a deterministic Signal row with exact_claim_if_adopted, if you "
                "cite that result, copy the field byte-for-byte into the evidence "
                "claim and every quantitative belief; do not round it, convert it "
                "to a percentage, or add approximate raw values. "
                "Respect measurement_context: numeric_sign is separate from categorical "
                "state, fraction differences use percentage points, and exact reported "
                "durations cannot become individual-quarter totals. "
                "Leave a retained Signal ref's prior claim untouched because its "
                "backing batch is no longer visible. Routing selection intents and "
                "need_transition_contract identify the exact owned need occurrences "
                "and expected scope, not proof that execution answered them. In this "
                "same response append exactly one need_dispositions row for each "
                "index in need_transition_contract.required_disposition_need_indices, "
                "and none for any other index. If that list is empty, keep "
                "need_dispositions=[]: a terminal closure may show the previous "
                "Signal batch without selecting any new direct-answer targets. "
                "Visible batch evidence and indexed remaining needs do not create "
                "ownership. Each row has exactly need_index (the zero-based "
                "prior need occurrence), answer_scope (full, partial, or unanswered), "
                "residual_need (1-300 characters for partial, null otherwise), "
                "evidence_refs (exact "
                "signal_ref/evidence_group/evidence_index tuples), and reason. Judge "
                "actual scope separately for the requested object, static attributes "
                "or terms, dynamic status, and the periods actually covered by "
                "executed evidence. Public availability bounds what was knowable "
                "but does not extend the fact's observation or coverage period. "
                "When narrowing a compound or umbrella need, preserve every "
                "unsupported requested facet and its time scope: static attributes "
                "do not replace dynamic status, and period-limited status does not "
                "settle later cutoff-bounded coverage. In reason, explain which "
                "requested facets and coverage the actual evidence answers and "
                "what remains missing; the reason never substitutes for the residual. Evidence refs "
                "must be exact current-batch tuples actually adopted by the final "
                "state; Routing expectations do not supply answer evidence. "
                "Signal measurement coverage does not determine need completion: a "
                "partial measurement may fully answer a narrow fact question, while "
                "a sufficient measurement may answer only one part of a compound "
                "question. An earlier period's facts do not answer a later period's "
                "question; a forecast already public at prediction_time may answer "
                "a question about that forecast. Full removes only the exact owned "
                "need; partial replaces it with the genuinely unanswered residual; "
                "unanswered preserves it byte-for-byte with residual_need=null. "
                "If every unsupported facet and time scope cannot fit losslessly "
                "in a genuinely narrower 1-300 character residual, choose unanswered "
                "with residual_need=null and keep the original need exactly; valid "
                "evidence may still be adopted independently. Do not delete a facet "
                "to meet the bound, leave it only in the reason, or create an "
                "unowned substitute need. "
                "The partial residual and its next_information_needs replacement "
                "must be exactly the same text. If correction feedback names a "
                "unique exact residual mirror dependency, synchronize only that "
                "authorized indexed slot when repairing the residual; this does "
                "not permit editing other needs or the whole array. "
                "Unanswered evidence_refs may be empty or cite valid adopted "
                "current-batch context explaining a period or scope mismatch; "
                "those refs do not claim the need was answered and never authorize "
                "closure. Unavailable, technically failed and "
                "context-only results cannot authorize completion. Preserve "
                "unselected occurrences and every unaddressed need; do not silently "
                "resolve a need or duplicate its full text inside a longer residual. "
                "Use research_state_capacity as advisory compression guidance: "
                "prefer staying within each field and combined state target given by "
                "new_item_capacity, and prefer compact evidence when capacity is "
                "zero. If reflection_runtime.must_finalize is true, this is the "
                "last executable evidence batch: return decision=finalize based only "
                "on accepted evidence, while preserving unresolved uncertainty in "
                "open_questions or next_information_needs. If every current-batch "
                "Signal is unavailable, preserve every prior ResearchState field and "
                "item byte-for-byte and change only decision to finalize. An "
                "unavailable Signal is not evidence of absence and cannot "
                "create a belief or resolve a "
                "question. "
                + SIGNAL_EXECUTION_STATUS_INSTRUCTION +
                "evaluation_context is control data, not evidence: every "
                "new or retained question must request only facts available by "
                "prediction_time. A cutoff-bounded question may ask what was already "
                "disclosed about a future schedule, but must not request later "
                "actuals, results, announcements, or updates. "
                "hypotheses, current_beliefs, contradictions, resolved_questions, "
                "open_questions, and next_information_needs are arrays of nonempty "
                "strings; never write an evidence object into one of them — new "
                "evidence goes to supporting_evidence with its own ref shape. "
                "When evaluation_anchor is supplied it is deterministic computed "
                "control data retained separately: use it to orient qualitative "
                "judgments and evidence needs, without numerical restatements in "
                "current_beliefs, contradictions or supporting_evidence. Percent changes must keep "
                "their explicit endpoint/target and named denominator consistent: "
                "baseline uses mean_adjusted_close, recent close uses recent_close. "
                "Doubling the baseline is a 100% gain from baseline. Computed metric summaries "
                "in computed_metrics are control data: use their qualitative "
                "implications for research, but never write them into current_beliefs, "
                "contradictions or supporting_evidence — evidence citations must come only from basic_info "
                "projections or current-batch Signal refs. Source catalog dates and filing-form "
                "identifiers are metadata, not literal issuer quotes. Interpret time-bound source wording "
                "at its available_at; do not present an expired event as current at "
                "prediction_time merely because the source said currently. "
                "When document_catalog is supplied you may spend bounded mid-call "
                "exchanges returning exactly "
                '{"inspect_document_catalog":{"cursor":20}} to read another '
                "bounded page. Copy next_cursor to advance, or select a valid "
                "integer offset from zero through counts.eligible to address a "
                "later page directly. Additional pages arrive in "
                "document_catalog_pages; previously supplied pages remain visible. "
                "Paging, fetching and computing share at most two exchanges total. "
                "You may return "
                '{"fetch_documents":[{"document_id":"supplied id",'
                '"section_id":"supplied id or omitted"}]} (at most two entries '
                "per exchange, no repeats) to read a bounded working view of a "
                "document or exact section through the point-in-time disclosure "
                "interface. A fitting unit is verbatim; an oversized unit retains "
                "its provenance and explicit omission markers, not its full body. "
                "fetched views arrive in document_channel and are retained for "
                "the final Predictor with their source provenance. Reading does "
                "not create a new ResearchState evidence kind or projection: "
                "State citations still require existing Basic Info or current-batch "
                "Signal refs. You may likewise return "
                '{"compute":[{"metric":"registered id","params":{...}}]} for any '
                "registered deterministic metric — price_shape(window_days "
                "30-365), return_between(from_offset_days>to_offset_days, "
                "1-365), distance_to_threshold(multiple 1.0-10.0, anchor "
                "relative) — the runtime computes it over point-in-time data "
                "and the computed card arrives in computed_metrics; it remains "
                "in the final control block. Use qualitative implications in State "
                "without restating or deriving its numbers. "
                "open_questions holds only material uncertainty that is not itself "
                "an actionable retrieval question; put every actionable retrieval "
                "question only in next_information_needs, never repeat an exact "
                "next_information_needs string in open_questions, and return "
                "open_questions=[] when every open question is already actionable "
                "there. Every numeric-bearing current_beliefs or contradictions "
                "item must copy one accepted supporting_evidence claim "
                "byte-for-byte. Retained Basic Info provenance stays unchanged "
                "while its claim may be restated."
                + _UNTRUSTED_DATA_INSTRUCTION
                + _SOURCE_FACT_RELATION_INSTRUCTION
                + _COMPUTED_PERIOD_INSTRUCTION
                + _PRICE_SHORTFALL_INSTRUCTION
                + PATCH_INSTRUCTION
            ),
            payload={
                "reflection_skill": plan.reflection_skill,
                **(
                    {"evaluation_anchor": dict(self.evaluation_anchor)}
                    if self.evaluation_anchor is not None
                    else {}
                ),
                **(
                    {"computed_metrics": [dict(card) for card in self.computed_metrics]}
                    if self.computed_metrics
                    else {}
                ),
                "research_state": state.to_dict(),
                "signal_batch": _signal_batch_model_view(batch),
                "signal_research_status": {result.ref: self.signal_research_status[result.ref]
                    for result in batch.results if result.ref in self.signal_research_status},
                "signal_evidence_ref_catalog": _signal_evidence_ref_catalog(batch),
                "executed_selection_intents": _reflection_selection_intents(
                    selections,
                    information_needs=state.next_information_needs,
                    evaluation_context=evaluation_context,
                ),
                "need_transition_contract": _reflection_need_transition_contract(
                    state,
                    selections,
                    batch,
                    evaluation_context=evaluation_context,
                ),
                "research_state_capacity": _research_state_capacity(state),
                "reflection_runtime": {
                    "must_finalize": must_finalize,
                    "termination_trigger": (
                        termination_trigger.value if termination_trigger else None
                    ),
                },
                "evaluation_context": evaluation_context,
            },
            parser=parse_reflected,
            allow_outcomes=False,
            max_output_tokens=ROLE_OUTPUT_TOKEN_LIMITS["controller"],
            max_request_tokens=self.request_token_budget,
            stable_correction_prefix=True,
            correction_guidance=_RESEARCH_STATE_CORRECTION_GUIDANCE,
            enforce_scoped_correction=True,
            exact_compaction_scope=True,
            output_patch_base=patch_base,
            patch_corrections=True,
            final_validation_fallback=_research_state_evidence_grounding_fallback,
        )
        if isinstance(reflect_caller, _DocumentChannelCaller) and reflect_caller.computed_metric_cards:
            self.set_computed_metrics([*self.computed_metric_cards, *reflect_caller.computed_metric_cards])
        return AgentStep(
            reflected, usage,
            metadata={"need_dispositions": disposition_metadata}
            if disposition_metadata is not None else {},
        )


def _explicit_signal_need_match_details(
    information_needs: tuple[str, ...], specs: Iterable[SignalSpec]
) -> tuple[dict[str, Any], ...]:
    """Locate version-owned exact need phrases without choosing a Signal locally."""

    normalized_needs = tuple(
        " "
        + re.sub(r"[^a-z0-9]+", " ", need.casefold()).strip()
        + " "
        for need in information_needs
    )
    matched: list[dict[str, Any]] = []
    for spec in specs:
        signal_ref = spec.ref
        tokens = tuple(
            token
            for token in re.sub(
                r"[^a-z0-9]+", " ", signal_ref.split(":", 1)[0].casefold()
            ).split()
            if token
        )
        ref_phrases = (
            (" " + " ".join(tokens) + " ",) if len(tokens) >= 3 else ()
        )
        configured_phrases = tuple(
            " " + re.sub(r"[^a-z0-9]+", " ", item.casefold()).strip() + " "
            for item in spec.parameters.get("routing_need_phrases", ())
            if isinstance(item, str) and item.strip()
        )
        direct_answer_phrases = tuple(
            item.strip()
            for item in spec.parameters.get("routing_answer_need_phrases", ())
            if isinstance(item, str) and item.strip()
        )
        phrases = (*ref_phrases, *configured_phrases)
        target_matches: list[dict[str, Any]] = []
        for need_index, need in enumerate(normalized_needs):
            if not any(phrase in need for phrase in phrases):
                continue
            target_match: dict[str, Any] = {
                "target_need_index": need_index,
                "matched_phrases": [
                    phrase.strip() for phrase in phrases if phrase in need
                ],
            }
            residual_facet_candidates = _routing_residual_facet_candidates(
                information_needs[need_index],
                direct_answer_phrases,
            )
            if residual_facet_candidates:
                target_match.update(
                    {
                        "answer_scope": "partial",
                        "residual_facet_candidates": list(
                            residual_facet_candidates
                        ),
                    }
                )
            target_matches.append(target_match)
        if target_matches:
            matched.append(
                {
                    "signal_ref": signal_ref,
                    "target_matches": target_matches,
                }
            )
    return tuple(matched)


def _signal_routing_research_context(
    state: ResearchState | None,
) -> dict[str, list[str]]:
    """Project ResearchState into a label-free applicability-only routing view."""

    if state is None:
        return {
            "hypotheses": [],
            "current_beliefs": [],
            "contradictions": [],
            "resolved_questions": [],
            "open_questions": [],
            "evidence_claims": [],
        }
    evidence_claims = tuple(
        dict.fromkeys(
            item.claim
            for item in state.supporting_evidence
            if isinstance(item, ResearchEvidenceRef)
        )
    )
    return {
        "hypotheses": list(state.hypotheses),
        "current_beliefs": list(state.current_beliefs),
        "contradictions": list(state.contradictions),
        "resolved_questions": list(state.resolved_questions),
        "open_questions": list(state.open_questions),
        "evidence_claims": list(evidence_claims),
    }


def _signal_routing_result_view(
    value: SignalResult | Mapping[str, Any],
    *, as_of: datetime | None = None,
) -> dict[str, Any]:
    """Return one prior conclusion without evidence literals or provenance."""

    model_view = signal_result_model_view(value, as_of=as_of)
    model_view["interpretation"] = {
        "summary": model_view["interpretation"]["summary"]
    }
    return {
        key: model_view[key]
        for key in (
            "signal_id",
            "version",
            "state",
            "interpretation",
            "status",
            "execution",
        )
        if key in model_view
    }


class LLMSignalRetrievalAgent:
    """One-step selector over unexecuted compact cards in one frozen Registry."""

    def __init__(self, caller: JSONRoleCaller) -> None:
        self.caller = caller
        self.request_token_budget: int | None = None
        self.evaluation_context: dict[str, str] | None = None
        self.deterministic_functions: Mapping[str, Callable[..., SignalResult]] | None = None

    def set_deterministic_functions(self, functions: Mapping[str, Callable[..., SignalResult]]) -> None:
        """Use the final executing callable map for card disclosure, including overrides."""

        self.deterministic_functions = dict(functions)

    def set_request_token_budget(self, value: int) -> None:
        self.request_token_budget = int(value)

    def set_evaluation_context(self, prediction_time: datetime) -> None:
        """Set the runtime-owned point-in-time horizon for the next selection."""

        if (
            prediction_time.tzinfo is None
            or prediction_time.utcoffset() is None
        ):
            raise ValidationError("prediction_time must be timezone-aware")
        normalized = prediction_time.astimezone(timezone.utc)
        self.evaluation_context = {
            "prediction_time": normalized.isoformat(),
            "horizon": "six_calendar_months",
            "horizon_end": _add_months(normalized.date(), 6).isoformat(),
        }

    def select(
        self,
        information_needs: tuple[str, ...],
        signal_registry: FrozenSignalRegistry,
        prior_signal_fingerprints: Mapping[str, tuple[str, ...]],
        prior_signal_results: Mapping[str, Mapping[str, Any]] | None = None,
        eligible_signal_refs: tuple[str, ...] | None = None,
        research_state: ResearchState | None = None,
        prior_context_tags: tuple[str, ...] = (),
    ) -> AgentStep[tuple[SignalSelectionDecision, ...]]:
        registry_refs = tuple(spec.ref for spec in signal_registry.specs)
        allowed_refs = (
            registry_refs
            if eligible_signal_refs is None
            else tuple(eligible_signal_refs)
        )
        if len(set(allowed_refs)) != len(allowed_refs):
            raise ValidationError("eligible Signal refs must be unique")
        if not set(allowed_refs).issubset(registry_refs):
            raise ValidationError("eligible Signal refs must belong to the Registry")
        if any(
            not isinstance(tag, str) or tag not in SIGNAL_CONTEXT_TAGS
            for tag in prior_context_tags
        ):
            raise ValidationError(
                "prior Signal routing context tags must use the frozen vocabulary"
            )
        normalized_prior_tags = tuple(dict.fromkeys(prior_context_tags))
        eligible = set(allowed_refs)
        research_context = _signal_routing_research_context(research_state)
        normalized_information_needs = tuple(
            " "
            + re.sub(r"[^a-z0-9]+", " ", need.casefold()).strip()
            + " "
            for need in information_needs
            if need.strip()
        )
        normalized_research_items = (
            *normalized_information_needs,
            *(
                " "
                + re.sub(r"[^a-z0-9]+", " ", text.casefold()).strip()
                + " "
                for values in research_context.values()
                for text in values
                if text.strip()
            ),
        )
        cards = []
        available_specs: list[SignalSpec] = []
        specs_by_ref = {spec.ref: spec for spec in signal_registry.specs}
        for spec in signal_registry.specs:
            if spec.ref not in eligible:
                continue
            required_research_phrases = tuple(
                str(phrase)
                for phrase in spec.parameters.get(
                    "routing_required_research_phrases", ()
                )
            )
            normalized_required = tuple(
                " "
                + re.sub(r"[^a-z0-9]+", " ", phrase.casefold()).strip()
                + " "
                for phrase in required_research_phrases
            )
            if required_research_phrases and not any(
                phrase in research_item
                for phrase in normalized_required
                for research_item in normalized_research_items
            ):
                continue
            excluded_tags = tuple(
                str(tag)
                for tag in spec.parameters.get(
                    "routing_excluded_context_tags", ()
                )
            )
            if set(normalized_prior_tags).intersection(excluded_tags):
                continue
            card = {
                "signal_ref": spec.ref,
                "category": spec.category,
                "description": spec.description,
                "execution_type": spec.execution_type.value,
                "measurement_scope": signal_measurement_scope(
                    spec, deterministic_functions=self.deterministic_functions),
            }
            from stock_opportunity_agent.memory.knowledge import usage_context

            card["usage_context"] = usage_context(_thaw_json(spec.parameters.get("usage_context")))
            profile = _thaw_json(signal_registry.learned_profiles.get(spec.ref, {}))
            from stock_opportunity_agent.memory.knowledge import empty_performance

            card["performance"] = profile.get("performance", empty_performance())
            status = _thaw_json(signal_registry.research_status.get(spec.ref, {}))
            if status:
                card["research_status"] = status
            if int(profile.get("unique_observations", 0) or 0) > 0:
                card["learned_profile"] = profile
            routing_phrases = spec.parameters.get("routing_need_phrases", ())
            if routing_phrases:
                card["routing_need_phrases"] = list(routing_phrases)
            if required_research_phrases:
                card["routing_required_research_phrases"] = list(
                    required_research_phrases
                )
            answer_need_phrases = spec.parameters.get(
                "routing_answer_need_phrases", ()
            )
            if answer_need_phrases:
                card["routing_answer_need_phrases"] = list(answer_need_phrases)
            if excluded_tags:
                card["routing_excluded_context_tags"] = list(excluded_tags)
            cards.append(card)
            available_specs.append(spec)
        if not cards:
            return AgentStep((), AgentUsage())

        allowed = {spec.ref for spec in available_specs}
        selection_payload: dict[str, Any] = {
            "available_signal_cards": cards,
            "information_needs": list(information_needs),
            "research_context": research_context,
            "previous_context_tags": list(normalized_prior_tags),
            "previous_signal_results": {
                ref: _signal_routing_result_view(value, as_of=_prediction_time_from_context(self.evaluation_context))
                for ref, value in (prior_signal_results or {}).items()
            },
            "learned_profile_default": "no committed observations",
            "performance_interpretation": "Observed-use correctness is case-weighted association, not causal credit; inspect applicability, failures and positive/negative-class counts.",
            "selection_caps": {"signals": 4, "llm_signals": 2},
        }
        if self.evaluation_context is not None:
            selection_payload["evaluation_context"] = dict(
                self.evaluation_context
            )
        explicit_empty_match_details = _explicit_signal_need_match_details(
            information_needs,
            available_specs,
        )
        explicit_empty_matches = tuple(
            str(item["signal_ref"]) for item in explicit_empty_match_details
        )
        def parse(value: Mapping[str, Any]) -> tuple[SignalSelectionDecision, ...]:
            if set(value) != {"selections"} or not isinstance(
                value.get("selections"), list
            ):
                raise StructuredValidationError(
                    [
                        ValidationIssue(
                            code="routing_portfolio_shape_invalid",
                            message="selection output requires selections array",
                            paths=("selections",),
                            allowed_repairs=("replace", "add"),
                        )
                    ]
                )
            raw_selections = value["selections"]
            if any(not isinstance(item, Mapping) for item in raw_selections):
                raise StructuredValidationError(
                    [
                        ValidationIssue(
                            code="routing_selection_shape_invalid",
                            message="every selection must be an object",
                            paths=(f"selections[{index}]",),
                            allowed_repairs=("replace", "remove", "quarantine"),
                        )
                        for index, item in enumerate(raw_selections)
                        if not isinstance(item, Mapping)
                    ]
                )
            if not raw_selections and explicit_empty_matches:
                raise StructuredValidationError(
                    [
                        ValidationIssue(
                            code="routing_required_match_omitted",
                            message=(
                                "empty Signal selection contradicts an exact "
                                "version-owned information-need phrase in the "
                                "available Signal cards, required_matches="
                                f"{list(explicit_empty_match_details)}. Return a "
                                "non-empty smallest batch targeted to one listed need"
                            ),
                            paths=("selections",),
                            source_refs=explicit_empty_matches,
                            allowed_repairs=("add",),
                        )
                    ]
                )
            required = {
                "signal_ref",
                "reason_code",
                "selection_reason",
                "applicability_hypothesis",
                "expected_role",
                "context_tags",
                "target_need_indices",
                "answer_scope",
                "residual_need",
            }
            allowed_reason_codes = {
                "answer_need",
                "confirm_hypothesis",
                "test_contradiction",
                "assess_applicability",
                "combine_evidence",
            }
            allowed_roles = {
                "primary",
                "confirmation",
                "contradiction",
                "coverage",
            }
            class IssueMessages(list[str]):
                def __init__(self) -> None:
                    super().__init__()
                    self.paths = ("selections",)
                    self.item_id: str | None = None
                    self.path_policy = "all"
                    self.repair_context: dict[str, Any] = {}
                    self.issues: list[ValidationIssue] = []
                    self.code = "routing_selection_invalid"
                    self.repairs = ("replace", "remove", "quarantine")

                def bind(
                    self,
                    paths: str | tuple[str, ...],
                    *,
                    item_id: str | None = None,
                    path_policy: str = "all",
                    repair_context: Mapping[str, Any] | None = None,
                    repairs: tuple[str, ...] = ("replace", "remove", "quarantine"),
                ) -> None:
                    self.paths = (paths,) if isinstance(paths, str) else paths
                    self.item_id = item_id
                    self.path_policy = path_policy
                    self.repair_context = dict(repair_context or {})
                    self.repairs = repairs

                def append(self, message: str) -> None:
                    super().append(message)
                    self.issues.append(
                        ValidationIssue(
                            code=self.code,
                            message=message,
                            paths=self.paths,
                            item_id=self.item_id,
                            item_id_field=(
                                "signal_ref" if self.item_id is not None else None
                            ),
                            path_policy=self.path_policy,
                            allowed_repairs=self.repairs,
                            source_refs=(
                                (self.item_id,) if self.item_id is not None else ()
                            ),
                            repair_context=self.repair_context,
                        )
                    )

            validation_errors = IssueMessages()
            diagnostic_items: list[dict[str, Any]] = []
            seen: set[str] = set()
            llm_count = 0
            for index, raw in enumerate(raw_selections):
                path = f"selections[{index}]"
                validation_errors.bind(path)
                item = dict(raw)
                missing = required - set(item)
                unexpected = set(item) - required
                if missing or unexpected:
                    validation_errors.bind(
                        tuple(
                            f"{path}.{field_name}"
                            for field_name in sorted((*missing, *unexpected))
                        ),
                        repairs=("add", "remove"),
                    )
                    validation_errors.append(
                        f"{path} requires exactly {sorted(required)}, "
                        f"missing={sorted(missing)}, "
                        f"unexpected={sorted(unexpected)}"
                    )
                if missing - {"context_tags"}:
                    continue
                if any(
                    not isinstance(item.get(name), str)
                    for name in required
                    - {
                        "context_tags",
                        "target_need_indices",
                        "answer_scope",
                        "residual_need",
                        "context_tags",
                    }
                ) or (
                    item["answer_scope"] is not None
                    and not isinstance(item["answer_scope"], str)
                ) or (
                    item["residual_need"] is not None
                    and not isinstance(item["residual_need"], str)
                ):
                    validation_errors.bind(path)
                    validation_errors.append(
                        f"{path} fields have invalid JSON types"
                    )
                    continue
                raw_context_tags = item.get("context_tags", [])
                if not isinstance(raw_context_tags, list) or any(
                    not isinstance(tag, str) for tag in raw_context_tags
                ):
                    validation_errors.bind(f"{path}.context_tags")
                    validation_errors.append(
                        f"{path}.context_tags must be a string array"
                    )
                    raw_context_tags = []
                target_need_indices = item["target_need_indices"]
                if not isinstance(target_need_indices, list) or any(
                    type(index) is not int for index in target_need_indices
                ):
                    validation_errors.bind(f"{path}.target_need_indices")
                    validation_errors.append(
                        f"{path}.target_need_indices must be an integer array"
                    )
                    continue
                signal_ref = item["signal_ref"]
                if signal_ref not in allowed:
                    validation_errors.bind(f"{path}.signal_ref")
                    validation_errors.append(
                        f"{path}.signal_ref={signal_ref!r} is outside supplied cards"
                    )
                    continue
                spec = specs_by_ref[signal_ref]
                if signal_ref in seen:
                    validation_errors.bind(path)
                    validation_errors.append(
                        f"{path}.signal_ref duplicates {signal_ref!r} in this batch"
                    )
                    continue
                seen.add(signal_ref)
                validation_errors.bind(path, item_id=signal_ref)
                if item["reason_code"] not in allowed_reason_codes:
                    validation_errors.bind(
                        f"{path}.reason_code", item_id=signal_ref
                    )
                    validation_errors.append(
                        f"{path}.reason_code={item['reason_code']!r} is unsupported"
                    )
                if item["expected_role"] not in allowed_roles:
                    validation_errors.bind(
                        f"{path}.expected_role", item_id=signal_ref
                    )
                    validation_errors.append(
                        f"{path}.expected_role={item['expected_role']!r} is unsupported"
                    )
                for name in ("selection_reason", "applicability_hypothesis"):
                    if not item[name].strip():
                        validation_errors.bind(
                            f"{path}.{name}", item_id=signal_ref
                        )
                        validation_errors.append(f"{path}.{name} must not be empty")
                target_shape_valid = (
                    len(target_need_indices) <= 1
                    and len(set(target_need_indices)) == len(target_need_indices)
                    and all(index >= 0 for index in target_need_indices)
                )
                if not target_shape_valid:
                    validation_errors.bind(
                        f"{path}.target_need_indices", item_id=signal_ref
                    )
                    validation_errors.append(
                        f"{path}.target_need_indices must contain at most one "
                        "unique non-negative integer"
                    )
                if (
                    target_shape_valid
                    and target_need_indices
                    and target_need_indices[0] >= len(information_needs)
                ):
                    validation_errors.bind(
                        f"{path}.target_need_indices", item_id=signal_ref
                    )
                    validation_errors.append(
                        f"{path}.target_need_indices is outside the supplied "
                        "information_needs array"
                    )
                if item["reason_code"] == "answer_need":
                    validation_errors.code = "routing_answer_ownership_invalid"
                    if len(target_need_indices) != 1:
                        validation_errors.bind(
                            f"{path}.target_need_indices", item_id=signal_ref
                        )
                        validation_errors.append(
                            f"{path} reason_code=answer_need requires exactly one "
                            "target_need_indices entry"
                        )
                    if item["answer_scope"] not in {"full", "partial"}:
                        validation_errors.bind(
                            f"{path}.answer_scope", item_id=signal_ref
                        )
                        validation_errors.append(
                            f"{path} reason_code=answer_need requires "
                            "answer_scope='full' or 'partial'"
                        )
                    elif item["answer_scope"] == "full":
                        if item["residual_need"] is not None:
                            validation_errors.bind(
                                f"{path}.residual_need", item_id=signal_ref
                            )
                            validation_errors.append(
                                f"{path} full answer requires residual_need=null"
                            )
                    else:
                        residual_need = item["residual_need"]
                        if (
                            not isinstance(residual_need, str)
                            or not residual_need.strip()
                            or len(residual_need.strip()) > 300
                        ):
                            validation_errors.bind(
                                f"{path}.residual_need", item_id=signal_ref
                            )
                            validation_errors.append(
                                f"{path} partial answer requires a 1-300 character "
                                "residual_need"
                            )
                        elif (
                            target_shape_valid
                            and len(target_need_indices) == 1
                            and target_need_indices[0] < len(information_needs)
                        ):
                            target_need = information_needs[target_need_indices[0]]
                            target_content = _normalized_need_content_tokens(
                                target_need
                            )
                            residual_content = _normalized_need_content_tokens(
                                residual_need
                            )
                            content_overlap = target_content & residual_content
                            answer_need_phrases = tuple(
                                str(phrase)
                                for phrase in spec.parameters.get(
                                    "routing_answer_need_phrases", ()
                                )
                            )
                            coordinated_residual_terms = (
                                _coordinated_residual_facet_terms(
                                    target_need,
                                    residual_need,
                                )
                            )
                            normalized_residual_need = (
                                " "
                                + re.sub(
                                    r"[^a-z0-9]+",
                                    " ",
                                    residual_need.casefold(),
                                ).strip()
                                + " "
                            )
                            normalized_target_need = (
                                " "
                                + re.sub(
                                    r"[^a-z0-9]+",
                                    " ",
                                    target_need.casefold(),
                                ).strip()
                                + " "
                            )
                            normalized_answer_need_phrases = tuple(
                                " "
                                + re.sub(
                                    r"[^a-z0-9]+", " ", phrase.casefold()
                                ).strip()
                                + " "
                                for phrase in answer_need_phrases
                                if re.sub(
                                    r"[^a-z0-9]+", " ", phrase.casefold()
                                ).strip()
                            )
                            residual_retains_direct_phrase = any(
                                phrase in normalized_residual_need
                                for phrase in normalized_answer_need_phrases
                            )
                            residual_removes_complete_direct_facet = (
                                not residual_retains_direct_phrase
                                and any(
                                    phrase in normalized_target_need
                                    and phrase not in normalized_residual_need
                                    for phrase in normalized_answer_need_phrases
                                )
                            )
                            removed_content = target_content - residual_content
                            cosmetic_residual = (
                                residual_need.strip() == target_need
                                or (
                                    target_content
                                    and len(content_overlap) / len(target_content)
                                    >= 0.9
                                    and not residual_removes_complete_direct_facet
                                )
                                or (
                                    residual_retains_direct_phrase
                                    and len(removed_content) <= 1
                                    and not coordinated_residual_terms
                                )
                            )
                            residual_facet_candidates = (
                                _routing_residual_facet_candidates(
                                    target_need,
                                    answer_need_phrases,
                                )
                                if cosmetic_residual
                                else ()
                            )
                            if not residual_content or (
                                len(content_overlap) / len(residual_content) < 0.5
                            ):
                                validation_errors.bind(
                                    f"{path}.residual_need", item_id=signal_ref
                                )
                                validation_errors.append(
                                    f"{path}.residual_need must be grounded in the "
                                    "targeted information need rather than copy or "
                                    "invent a different need. The targeted need is: "
                                    f"\"{target_need}\". Write the corrected "
                                    "residual as one unresolved clause of that "
                                    "exact need, kept inside its own as-of bound, "
                                    "minus the facet this Signal answered"
                                )
                            target_bound = _need_as_of_bound_clause(target_need)
                            routing_prediction_date = (
                                _prediction_time_from_context(
                                    self.evaluation_context
                                )
                            )
                            if routing_prediction_date is not None:
                                unrepresentable_residual = (
                                    _bounded_residual_need(
                                        residual_need,
                                        target_need,
                                        routing_prediction_date,
                                    )
                                    is None
                                )
                                repair_bound = _need_as_of_bound_clause(
                                    target_need,
                                    routing_prediction_date,
                                )
                            else:
                                unrepresentable_residual = (
                                    target_bound is not None
                                    and bool(
                                        _future_source_date_refs(
                                            residual_need,
                                            target_bound[1],
                                            field_name=(
                                                "next_information_needs"
                                            ),
                                        )
                                    )
                                )
                                repair_bound = target_bound
                            if unrepresentable_residual:
                                inherited_cutoff = (
                                    repair_bound[0]
                                    if repair_bound is not None
                                    else None
                                )
                                if inherited_cutoff is None:
                                    symbolic_bound = (
                                        _SYMBOLIC_AS_OF_BOUND.search(target_need)
                                    )
                                    inherited_cutoff = (
                                        symbolic_bound.group(0)
                                        if symbolic_bound is not None
                                        else None
                                    )
                                inherited_expectation = (
                                    _INHERITABLE_EXPECTATION_CONTEXT.search(
                                        target_need
                                    )
                                )
                                repair_context = {
                                    "target_need_cutoff_clause": inherited_cutoff,
                                }
                                if routing_prediction_date is not None:
                                    repair_context["prediction_time"] = (
                                        routing_prediction_date.isoformat()
                                    )
                                if inherited_expectation is not None:
                                    repair_context[
                                        "target_need_expectation_marker"
                                    ] = inherited_expectation.group(0)
                                scope_phrase = (
                                    "the actual prediction-time boundary "
                                    + routing_prediction_date.isoformat()
                                    if routing_prediction_date is not None
                                    else (
                                        "the target's as-of cutoff clause "
                                        + repr(inherited_cutoff)
                                    )
                                )
                                if (
                                    routing_prediction_date is not None
                                    and inherited_cutoff is not None
                                ):
                                    scope_phrase += (
                                        " (the target's cutoff clause is "
                                        + repr(inherited_cutoff)
                                        + ")"
                                    )
                                restate_phrase = (
                                    "Restate the same unresolved facets while "
                                    "retaining that exact cutoff clause and "
                                    "the target's forward expectation or "
                                    "schedule framing"
                                    + (
                                        " (for example its "
                                        + repr(
                                            inherited_expectation.group(0)
                                        )
                                        + " wording)"
                                        if inherited_expectation is not None
                                        else ""
                                    )
                                    + ", or narrow to facets that stay inside it"
                                    if inherited_cutoff is not None
                                    else (
                                        "The target need declares no cutoff "
                                        "clause this residual can inherit, so "
                                        "narrow the residual to facets that "
                                        "already stay inside the target's own "
                                        "scope"
                                    )
                                )
                                validation_errors.bind(
                                    (f"{path}.residual_need",),
                                    item_id=signal_ref,
                                    repair_context=repair_context,
                                )
                                validation_errors.append(
                                    f"{path}.residual_need dropped the targeted "
                                    "need's temporal scope: it requests calendar "
                                    "scope beyond " + scope_phrase + ". "
                                    + restate_phrase
                                    + ". Runtime will not persist an "
                                    "unbounded residual that the prediction-time "
                                    "boundary must later reject"
                                )
                            if cosmetic_residual:
                                cosmetic_paths = [f"{path}.residual_need"]
                                if not residual_facet_candidates:
                                    cosmetic_paths.append(f"{path}.answer_scope")
                                cosmetic_paths.append(path)
                                validation_errors.bind(
                                    tuple(cosmetic_paths),
                                    item_id=signal_ref,
                                    repair_context=(
                                        {
                                            "residual_facet_candidates": list(
                                                residual_facet_candidates
                                            )
                                        }
                                        if residual_facet_candidates
                                        else None
                                    ),
                                )
                                validation_errors.append(
                                    f"{path}.residual_need must remove the answered "
                                    "facet rather than retain the target cosmetically"
                                    + (
                                        ", residual_facet_candidates="
                                        + json.dumps(
                                            list(residual_facet_candidates),
                                            separators=(",", ":"),
                                        )
                                        + ". Use only these literal unresolved "
                                        "target clauses when writing the corrected "
                                        "natural-language residual"
                                        if residual_facet_candidates
                                        else (
                                            f", and {path}.answer_scope must change "
                                            "from partial: use full with a null "
                                            "residual only if the card covers the "
                                            "complete target, otherwise use a "
                                            "contextual reason or remove the selection"
                                        )
                                    )
                                    + (
                                        f". If exact scope remains uncertain, change "
                                        f"{path} to a contextual reason with "
                                        "answer_scope=null and residual_need=null, "
                                        "or remove that complete selection"
                                    )
                                )
                            if cosmetic_residual:
                                coordinated_residual_terms = ()
                            reason_content = _normalized_need_content_tokens(
                                item["selection_reason"]
                            )
                            conflicting_coordinated_terms = [
                                term
                                for term in coordinated_residual_terms
                                if term in reason_content
                            ]
                            if conflicting_coordinated_terms:
                                validation_errors.bind(
                                    (f"{path}.selection_reason", path),
                                    item_id=signal_ref,
                                    repair_context={
                                        "remove_terms_from_selection_reason": (
                                            conflicting_coordinated_terms
                                        )
                                    },
                                )
                                validation_errors.append(
                                    f"{path}.selection_reason claims explicit "
                                    "alternative facets retained by residual_need, "
                                    "residual_facet_terms="
                                    f"{json.dumps(conflicting_coordinated_terms, separators=(',', ':'))}, "
                                    "remove_terms_from_selection_reason="
                                    f"{json.dumps(conflicting_coordinated_terms, separators=(',', ':'))}. "
                                    "Remove every listed residual-only term from "
                                    "selection_reason, name only the answered "
                                    "counterpart, and leave unresolved facets only "
                                    "in residual_need. If that distinction cannot be "
                                    f"stated exactly, change {path} to a contextual "
                                    "reason with answer_scope=null and "
                                    "residual_need=null, or remove that complete "
                                    "selection"
                                )
                            else:
                                residual_scope_values = (
                                    residual_facet_candidates
                                    if cosmetic_residual
                                    else (residual_need,)
                                )
                                shared_residual_phrase = next(
                                    (
                                        phrase
                                        for residual_scope in residual_scope_values
                                        if (
                                            phrase := _shared_distinctive_phrase(
                                                item["selection_reason"],
                                                residual_scope,
                                                target_need=target_need,
                                            )
                                        )
                                    ),
                                    None,
                                )
                            if (
                                not coordinated_residual_terms
                                and shared_residual_phrase is not None
                            ):
                                remove_terms = shared_residual_phrase.split()
                                validation_errors.bind(
                                    (f"{path}.selection_reason", path),
                                    item_id=signal_ref,
                                    repair_context={
                                        "remove_terms_from_selection_reason": (
                                            remove_terms
                                        )
                                    },
                                )
                                validation_errors.append(
                                    f"{path}.selection_reason claims a facet retained "
                                    "by residual_need via shared phrase "
                                    f"{shared_residual_phrase!r}, "
                                    "remove_terms_from_selection_reason="
                                    f"{json.dumps(remove_terms, separators=(',', ':'))}. "
                                    "Remove every listed residual-only term from "
                                    "selection_reason and name only the answered "
                                    "facet, leaving unresolved facets only in "
                                    "residual_need. If that distinction cannot be "
                                    f"stated exactly, change {path} to a contextual "
                                    "reason with answer_scope=null and "
                                    "residual_need=null, or remove that complete "
                                    "selection"
                                )
                elif (
                    item["answer_scope"] is not None
                    or item["residual_need"] is not None
                ):
                    validation_errors.bind(
                        (f"{path}.answer_scope", f"{path}.residual_need"),
                        item_id=signal_ref,
                    )
                    validation_errors.append(
                        f"{path} non-answer reason requires answer_scope=null and "
                        "residual_need=null"
                    )
                validation_errors.code = "routing_selection_invalid"
                tags: list[str] = []
                for raw_tag in raw_context_tags:
                    tag = re.sub(
                        r"[^a-z0-9_:-]+", "_", raw_tag.casefold()
                    ).strip("_")[:48]
                    if tag not in SIGNAL_CONTEXT_TAGS:
                        continue
                    if tag not in tags:
                        tags.append(tag)
                    if len(tags) == 4:
                        break
                if spec.execution_type.value == "llm":
                    if llm_count >= 2:
                        continue
                    llm_count += 1
                diagnostic_items.append(
                    {
                        "index": index,
                        "signal_ref": signal_ref,
                        "reason_code": item["reason_code"],
                        "selection_reason": item["selection_reason"].strip()[:240],
                        "applicability_hypothesis": item[
                            "applicability_hypothesis"
                        ].strip()[:240],
                        "expected_role": item["expected_role"],
                        "context_tags": tuple(tags),
                        "target_need_indices": tuple(target_need_indices),
                        "answer_scope": item["answer_scope"],
                        "residual_need": (
                            item["residual_need"].strip()
                            if isinstance(item["residual_need"], str)
                            else None
                        ),
                        "target_shape_valid": target_shape_valid,
                    }
                )
                if len(diagnostic_items) == 4:
                    break
            direct_targets: dict[int, list[dict[str, Any]]] = {}
            for item in diagnostic_items:
                if (
                    item["reason_code"] == "answer_need"
                    and item["target_shape_valid"]
                    and len(item["target_need_indices"]) == 1
                ):
                    direct_targets.setdefault(
                        item["target_need_indices"][0], []
                    ).append(item)
            for target_index, owners in direct_targets.items():
                if len(owners) < 2:
                    continue
                full_owners = [item for item in owners if item["answer_scope"] == "full"]
                retained = full_owners[0] if len(full_owners) == 1 else None
                for item in owners:
                    if item is retained:
                        continue
                    validation_errors.code = "routing_answer_conflict"
                    validation_errors.bind(
                        f"selections[{item['index']}]", item_id=item["signal_ref"],
                        repair_context={"mechanical_action": "context_only_selection"},
                    )
                    validation_errors.append(
                        "one routing round permits at most one direct answer for "
                        f"information_needs[{target_index}]. Retain this selected "
                        "Signal for context only; no alternative answer is inferred"
                    )
            validation_errors.code = "routing_selection_invalid"
            selector_case_tags = {
                *normalized_prior_tags,
                *(
                    tag
                    for item in diagnostic_items
                    for tag in item["context_tags"]
                ),
            }
            for item in diagnostic_items:
                path = f"selections[{item['index']}]"
                signal_ref = item["signal_ref"]
                validation_errors.bind(path, item_id=signal_ref)
                excluded_tags = sorted(
                    selector_case_tags.intersection(
                        specs_by_ref[signal_ref].parameters.get(
                            "routing_excluded_context_tags", ()
                        )
                    )
                )
                if excluded_tags:
                    validation_errors.append(
                        "Signal selection applicability contradicts a version-owned "
                        f"routing exclusion at {path}: {signal_ref} cannot be selected "
                        "after the selector classified this case with "
                        f"context_tags={excluded_tags}. Remove the incompatible "
                        "selection. Runtime will not infer a replacement Signal or "
                        "forget an earlier accepted case classification"
                    )
                required_phrases = tuple(
                    str(phrase)
                    for phrase in specs_by_ref[signal_ref].parameters.get(
                        "routing_required_research_phrases", ()
                    )
                )
                normalized_required = tuple(
                    " "
                    + re.sub(
                        r"[^a-z0-9]+", " ", phrase.casefold()
                    ).strip()
                    + " "
                    for phrase in required_phrases
                )
                if required_phrases and not any(
                    phrase in research_item
                    for phrase in normalized_required
                    for research_item in normalized_research_items
                ):
                    validation_errors.append(
                        "Signal selection lacks version-owned required research "
                        f"context at {path}: {signal_ref} requires at least one exact "
                        "phrase already present in information_needs or accepted "
                        f"research_context from {list(required_phrases)}. Remove "
                        "the incompatible selection. Runtime will not accept a "
                        "new analogy stated only in selection_reason or "
                        "applicability_hypothesis"
                    )
                answer_need_phrases = tuple(
                    str(phrase)
                    for phrase in specs_by_ref[signal_ref].parameters.get(
                        "routing_answer_need_phrases", ()
                    )
                )
                normalized_answer_need_phrases = tuple(
                    " "
                    + re.sub(
                        r"[^a-z0-9]+", " ", phrase.casefold()
                    ).strip()
                    + " "
                    for phrase in answer_need_phrases
                )
                if (
                    item["reason_code"] == "answer_need"
                    and answer_need_phrases
                    and item["target_shape_valid"]
                    and len(item["target_need_indices"]) == 1
                    and 0
                    <= item["target_need_indices"][0]
                    < len(normalized_information_needs)
                    and not any(
                        phrase
                        in normalized_information_needs[
                            item["target_need_indices"][0]
                        ]
                        for phrase in normalized_answer_need_phrases
                    )
                ):
                    validation_errors.append(
                        "Signal selection reason_code=answer_need lacks a "
                        f"version-owned direct-need phrase at {path}: "
                        f"{signal_ref} requires at least one exact "
                        "phrase in its one targeted information need from "
                        f"{list(answer_need_phrases)}. Point "
                        "target_need_indices at an information need that already "
                        "contains one listed phrase byte-for-byte (the needs "
                        "themselves are not editable in this output), or change "
                        "reason_code to an accurate contextual code such as "
                        "combine_evidence, or remove the selection. "
                        "research_context and selector-authored prose cannot "
                        "turn context into an answered need"
                    )
            if validation_errors:
                raise StructuredValidationError(validation_errors.issues)
            return tuple(
                SignalSelectionDecision(
                    signal_ref=item["signal_ref"],
                    reason_code=item["reason_code"],
                    selection_reason=item["selection_reason"],
                    applicability_hypothesis=item["applicability_hypothesis"],
                    expected_role=item["expected_role"],
                    context_tags=item["context_tags"],
                    target_need_indices=item["target_need_indices"],
                    answer_scope=item["answer_scope"],
                    residual_need=item["residual_need"],
                )
                for item in diagnostic_items
            )

        selected, usage = _complete_parsed_role(
            self.caller,
            stage="signal_retrieval_cards",
            system_prompt=(
                "Choose the smallest unique batch from available_signal_cards. "
                "measurement_scope copies the exact version retrieval requirements and "
                "separately discloses its actual executing callable contract/configured "
                "parameters when known. Comparison prose does not override execution; "
                "unknown documentation is not evidence of missing issuer data. The "
                "research_status authorizes a technically admitted measurement's use "
                "while its effect remains unverified. Select by need and applicability; "
                "admission does not establish predictive benefit. "
                "cards are already versioned, eligible, and unexecuted; never recreate "
                "omitted refs. Check previous_signal_results and their recorded "
                "execution status. An unavailable-shaped result alone does not "
                "establish missing issuer data or justify excluding another Signal "
                "with the same data requirement. For domain_unavailable, assess "
                "whether the sibling has a specific basis to find useful evidence. "
                + SIGNAL_EXECUTION_STATUS_INSTRUCTION +
                "For research_context, use it only to test Signal "
                "applicability; it is accepted controller context, not source evidence. "
                "Preserve previous_context_tags "
                "when applying card exclusions. Return {\"selections\": []} only when "
                "no card adds useful evidence; an exact runtime-supplied name or "
                "routing_need_phrases match requires a non-empty answer. Card "
                "routing_excluded_context_tags and routing_required_research_phrases "
                "are hard applicability rules. routing_answer_need_phrases is stricter: "
                "answer_need requires its exact phrase in the one targeted need. New "
                "selector prose cannot create applicability. Use "
                "routing answer_scope as intended measurement capability, not proof "
                "that issuer data is available or the need is already answered; "
                "Reflect must verify the actual executed evidence. A callable that "
                "selects the latest comparable pair does not thereby support an "
                "arbitrarily requested period or share basis. Use "
                "reason_code=answer_need only when the description and "
                "measurement_scope directly cover the explicit object, period, unit "
                "and comparison facet under the actual callable contract when known; "
                "other useful cards are contextual. Missing or conflicting capability "
                "cannot justify full scope, and declared scope does not prove issuer "
                "data is available. "
                "answer_scope=full only when every facet is covered. partial requires "
                "residual_need "
                "containing only unresolved facets, not a cosmetic restatement or a "
                "different need; it must not copy a different information_needs item. "
                "selection_reason must describe only the answered facet: the shared "
                "research topic may appear, but do not repeat a distinctive "
                "multi-word phrase or several residual-only terms from residual_need. "
                "Use at most one answer_need selection per target. Non-empty "
                "selection items "
                "contain exactly: signal_ref; reason_code (answer_need, "
                "confirm_hypothesis, test_contradiction, assess_applicability, "
                "or combine_evidence); a <=240 character selection_reason; a "
                "<=240 character applicability_hypothesis; expected_role "
                "(primary, confirmation, contradiction, or coverage); and a "
                "target_need_indices array containing at most one integer; "
                "answer_scope (full, partial, or null); residual_need (a <=300 "
                "character string only for partial, otherwise null); and a required "
                "context_tags array containing zero to four values from the frozen "
                "vocabulary below. "
                "answer_need requires one valid information_needs index. Other reasons "
                "use zero or one association index and null answer scope/residual; this "
                "does not answer the need. context_tags values are: general, "
                "comparable_financials, sparse_evidence, filing_rich, news_rich, "
                "transcript_available, market_data_only, pre_revenue, "
                "early_commercialization, scaling, mature_operations, "
                "project_driven, recurring_revenue, customer_concentrated, "
                "capital_intensive, cyclical, regulated, biotechnology, "
                "healthcare, software, semiconductors, hardware, industrial, "
                "energy, materials, consumer, financials, real_estate, "
                "communications, small_cap, mid_cap, large_cap, high_volatility, "
                "or catalyst_window."
                + (
                    " evaluation_context is control data, not evidence: its "
                    "prediction_time is the actual runtime cutoff. Keep a "
                    "partial residual_need inside that boundary by requesting "
                    "only facts already available by prediction_time, never "
                    "later actuals, results, or updates."
                    if self.evaluation_context is not None
                    else ""
                )
                + _UNTRUSTED_DATA_INSTRUCTION
                + _SOURCE_FACT_RELATION_INSTRUCTION
            ),
            payload=selection_payload,
            parser=parse,
            allow_outcomes=False,
            max_output_tokens=2_000,
            max_request_tokens=self.request_token_budget,
            stable_correction_prefix=True,
            enforce_scoped_correction=True,
            patch_corrections=True,
            final_validation_fallback=_routing_context_only_fallback,
        )
        return AgentStep(selected, usage)


_PREDICTOR_ROLE_AUTHORITY = (
    "Signal research_status=admitted with effect_status=unverified authorizes "
    "measurement use, not a claim of prediction benefit. A magnitude research "
    "purpose never mechanically selects a larger magnitude class. "
    "H_analyse guides evidence organization and weighting. The fixed Predictor "
    "shell owns final candidate_judgment and conditional magnitude classification. "
    "The shell's required output overrides any Plan instruction to omit "
    "classification or prediction; leaving classification to the shell does "
    "not remove that system capability. "
    "When present, runtime_termination describes collection control independently "
    "of the controller decision: budget or no-match stops and unresolved needs "
    "remain information limitations; finalize alone does not mean all questions "
    "were answered. "
)


_BLIND_PREDICTOR_SYSTEM_PROMPT = (
    "Use final_context.prediction_time as the exact forecast boundary and "
    "each source card available_at to distinguish historical source wording "
    "from conditions established as current. Using only the anonymous supplied "
    "context, predict whether the "
    "target security's adjusted share price reaches at least 2x over "
    "the next six calendar months. The prediction-time baseline is the "
    "mean adjusted close over the last five complete trading days, and "
    "the future numerator is the maximum mean adjusted close over any "
    "five complete consecutive trading days inside that horizon. This "
    "runtime-computed point-in-time mean is supplied as "
    "final_context.prediction_baseline. When naming the current or "
    "baseline price or computing target upside, use that supplied mean; "
    "do not relabel an older cited price observation as current. Any percent "
    "gain to a numeric target or doubling threshold must use its explicitly "
    "named denominator: baseline means mean_adjusted_close, recent close means "
    "recent_close. These are distinct anchors; doubling the baseline is a 100% "
    "gain from that baseline. This "
    "also means market data is not absent when prediction_baseline has "
    "status=available; distinguish missing forward projections or other "
    "specific gaps from the supplied price baseline. The baseline and doubling "
    "threshold define the outcome: being near half that threshold is expected "
    "by construction and is not independent counter-evidence against a surge. "
    "Use supplied computed_metrics for quantitative price-trend statements; "
    + _COMPUTED_PERIOD_INSTRUCTION +
    _PRICE_SHORTFALL_INSTRUCTION +
    "keep each computed return with that card's own first/last prices and dates, "
    "rather than attaching an unrelated Basic Info price. "
    + SIGNAL_EXECUTION_STATUS_INSTRUCTION +
    "Respect Signal "
    "measurement_context: categorical states are not stock-direction forecasts, "
    "numeric_sign is distinct from the measured predicate's categorical state; "
    "a fraction_difference display uses percentage points, not percent, "
    "with the producer's formula and exact reported period, "
    "and dated cumulative financial observations are not individual-quarter totals. "
    "do not call a price change a doubling unless a computed card verifies it. "
    "If the needed computed window is absent, keep that comparison uncertain. This "
    "is a stock-price repricing outcome, not a requirement that revenue, "
    "earnings, users, production, or another operating metric doubles; "
    "use those measures only as evidence about possible share-price "
    "repricing. This is a forecast under uncertainty, not a proof task. "
    "Do not require a guarantee, certainty, or an explicit future price "
    "target. Return candidate_judgment=likely or possible when the supplied "
    "evidence makes the security an evidence-backed opportunity candidate "
    "for the defined price outcome within the horizon, and express "
    "residual doubt through confidence and uncertainties. Possible is a "
    "screening judgment: it does not require a quantified valuation bridge "
    "or a proven, concrete path to 2x. Source-backed expectation-changing "
    "acceleration, a material catalyst, or early market confirmation can "
    "support possible even when the exact financial impact remains "
    "uncertain. For candidate_judgment=likely or possible, at least one "
    "key_reasons item must affirmatively connect supplied source-backed "
    "evidence to a credible candidate for this exact price outcome. "
    "Counter-evidence may appear in other reasons or uncertainties, but "
    "do not return a positive judgment when every key reason explicitly "
    "denies support for 2x, doubling, surge, or repricing. Return "
    "candidate_judgment=unlikely when contrary evidence "
    "makes the outcome unlikely, or candidate_judgment="
    "insufficient_information when the packet lacks source-backed positive "
    "evidence; do not choose a negative judgment merely because certainty, "
    "a future price target, "
    "or a complete valuation bridge is unavailable. These evaluation cases "
    "are deliberately "
    "outcome-stratified and do not represent the live-market base rate, "
    "so do not predict false merely because 2x moves are rare in the "
    "broad market. Make the independent case-level decision from the "
    "supplied evidence. This is an opportunity-discovery classifier: "
    "choose likely or possible when the security looks like a candidate "
    "for that exact 2x price outcome, even though doubling need not be more "
    "than 50% probable. Choose unlikely or insufficient_information when "
    "the corresponding negative condition applies. For likely or possible, "
    "choose magnitude 2-3x, 3-10x, or 10x+; otherwise magnitude must be "
    "null. The fixed six-month definition overrides any "
    "conflicting horizon in the supplied evolvable analysis prompt. Do "
    "not use web tools."
    + _PREDICTOR_ROLE_AUTHORITY
    + _UNTRUSTED_DATA_INSTRUCTION
    + _SOURCE_FACT_RELATION_INSTRUCTION
    + _BLIND_PREDICTION_OUTPUT
)


class LLMBlindPredictor:
    """No-web two-stage Predictor plus explicitly post-hoc reflection adapter."""

    def __init__(
        self,
        caller: JSONRoleCaller,
        *,
        anonymous_aliases: Iterable[str] = (),
    ) -> None:
        registration = getattr(caller, "registration", None)
        if registration is not None and registration.web_tools_allowed:
            raise ValidationError("Blind Predictor model registration must be no-web")
        self.caller = caller
        self.anonymous_aliases = tuple(anonymous_aliases)
        self.request_token_budget: int | None = None

    def set_request_token_budget(self, value: int) -> None:
        self.request_token_budget = int(value)

    def estimate_prediction_tokens(self, final_context: Mapping[str, Any]) -> int | None:
        """Reserve the same anonymous initial request that predict will send."""

        runtime_termination_view(final_context)
        _require_context_signal_pit(final_context)
        estimator = getattr(self.caller, "estimate_json_request_tokens", None)
        if not callable(estimator):
            return None
        return estimator(
            system_prompt=_BLIND_PREDICTOR_SYSTEM_PROMPT + _INCREMENTAL_ROLE_INSTRUCTION,
            payload={"final_context": dict(final_context)},
            allow_outcomes=False,
            anonymous_aliases=self.anonymous_aliases,
            max_output_tokens=2_000,
        )

    def predict(self, final_context: Mapping[str, Any]) -> AgentStep[BlindPrediction]:
        runtime_termination_view(final_context, require_ready=True)
        _require_context_signal_pit(final_context)
        prediction, usage = _complete_parsed_role(
            self.caller,
            stage="blind_predictor_predict",
            system_prompt=_BLIND_PREDICTOR_SYSTEM_PROMPT,
            payload={"final_context": dict(final_context)},
            parser=lambda value: _blind_prediction_with_baseline(
                value, final_context
            ),
            allow_outcomes=False,
            anonymous_aliases=self.anonymous_aliases,
            max_output_tokens=2_000,
            max_request_tokens=self.request_token_budget,
            enforce_scoped_correction=True,
            patch_corrections=True,
        )
        return AgentStep(prediction, usage)

    def reflect(
        self,
        original_context: Mapping[str, Any],
        original_prediction: BlindPrediction,
        ground_truth: GroundTruth,
    ) -> AgentStep[PredictionSelfReflection]:
        _scan_payload(
            {"original_context": dict(original_context)},
            allow_outcomes=False,
            anonymous_aliases=self.anonymous_aliases,
        )
        try:
            framework_correct = (
                original_prediction.is_surge == ground_truth.is_surge
                and (
                    not ground_truth.is_surge
                    or original_prediction.magnitude is ground_truth.magnitude
                )
            )
            judgment_feedback = candidate_judgment_feedback(
                original_prediction,
                ground_truth,
            )
            magnitude_block = magnitude_feedback(
                original_prediction,
                ground_truth,
            )
            jev_feedback = jev_decision_feedback(
                original_prediction,
                ground_truth,
            )
            compact_context = _compact_posthoc_context(original_context)
            source_identity = "case:" + _canonical_hash({
                "context": compact_context,
                "prediction": original_prediction.to_dict(),
                "judgment_feedback": judgment_feedback,
                "magnitude_feedback": magnitude_block,
            })
            source_snapshot = {
                "source_identity": source_identity,
                "candidate_judgment_feedback": judgment_feedback,
                "magnitude_feedback": magnitude_block,
                **({"jev_decision_feedback": jev_feedback} if jev_feedback else {}),
            }
            source_index = ReflectionMemoryIndex.from_case_rows(
                [source_snapshot], owner_ref=source_identity,
            )

            def validate_case_text(items: tuple[Any, ...]) -> None:
                rows = tuple(
                    (f"reflection_items[{position}].{field}", text)
                    for position, item in enumerate(items) for field in ("brief", "detail")
                    if isinstance(text := (item.get(field) if isinstance(item, Mapping)
                                          else getattr(item, field, None)), str)
                )
                issues = _price_reasoning_issues(
                    rows,
                    compact_context.get("prediction_baseline"),
                )
                issues.extend(_measurement_reasoning_issues(
                    rows,
                    _context_signal_results(compact_context),
                ))
                issues.extend(_computed_period_issues(
                    rows,
                    compact_context.get("computed_metrics", ()),
                ))
                issues.extend(_realized_outcome_issues(rows,
                    compact_context.get("prediction_baseline"), ground_truth.to_dict()))
                for path, text in rows:
                    if _market_data_absence_paths(((path, (text,)),), compact_context.get("prediction_baseline")):
                        issues.append(ValidationIssue(
                            code="reflection_market_data_available", paths=(path,),
                            message="Market data was supplied: compact_context.prediction_baseline.status='available'; narrow the gap to missing forward projections or other absent evidence",
                        ))
                if issues:
                    raise StructuredValidationError(issues)

            def parse_reflection(value: Mapping[str, Any]) -> PredictionSelfReflection:
                items, _selected, projection = _structured_reflection_items(
                    value, index=source_index, level="case", owner_ref=source_identity,
                    item_validator=validate_case_text,
                )
                return PredictionSelfReflection(
                    correct=framework_correct,
                    **projection,
                    reflection_items=items,
                    source_identity=source_identity,
                    source_snapshot=source_snapshot,
                )

            reflection, usage = _complete_parsed_role(
                self.caller,
                stage="blind_predictor_posthoc_reflect",
                system_prompt=(
                    "The saved prediction is immutable. Given its original anonymous "
                    "compact context and newly revealed truth, reflect on the prediction. "
                    "framework_prediction_correct is deterministic and immutable; "
                    "runtime preserves it, so do not return or rejudge it. "
                    "Use candidate_judgment_feedback to distinguish binary errors, "
                    "conservative but binary-correct calls, and evidence-coverage "
                    "gaps; that feedback covers Stage 1 only, while framework "
                    "correctness also checks magnitude for a true surge. The "
                    "magnitude_feedback block separates those error kinds "
                    "deterministically: classify each miss first as a direction "
                    "error (missed_surge or binary false positive) or a class "
                    "error (underestimate or overestimate), then attribute "
                    "causes. Magnitude diagnostics never change the copied "
                    "correctness bit or any saved field. Do not "
                    "rewrite the saved four-way judgment or infer that "
                    "one realized outcome proves an ex-ante probability category. "
                    "When jev_decision_feedback is present, use its probabilities "
                    "and confidence only as provider decision signals for diagnosing "
                    "calibration, overconfidence, conservatism, or class confusion; "
                    "do not call them calibrated live-market probabilities. Its "
                    "calibration assessment is deterministic: a correct_low_support "
                    "case warrants inspecting why the realized class received little "
                    "probability; a high-confidence error warrants a testable "
                    "explanation, not an invented cause. Do not reward confidence "
                    "merely for increasing. Record known error facts separately "
                    "from causal hypotheses. A correct prediction does not prove "
                    "that its reasons caused the outcome or were sufficient. "
                    "When compact_context.prediction_baseline "
                    "has status=available, do not claim market data is absent or was "
                    "not provided; distinguish missing forward projections or other "
                    "specific gaps from the supplied price baseline. Check numeric "
                    "claims in every brief and detail against the supplied runtime "
                    "anchor, including linked endpoints/percent changes. A gain "
                    "from baseline uses mean_adjusted_close; a gain from recent "
                    "close uses recent_close. Doubling the baseline is a 100% gain "
                    "from baseline. Do not copy incorrect saved numerical reasoning "
                    "as a fact; the saved prediction remains immutable."
                    + _UNTRUSTED_DATA_INSTRUCTION
                    + _SOURCE_FACT_RELATION_INSTRUCTION
                    + _COMPUTED_PERIOD_INSTRUCTION
                    + _PRICE_SHORTFALL_INSTRUCTION
                    + _REALIZED_OUTCOME_INSTRUCTION
                    + _structured_reflection_contract("case")
                ),
                payload={
                    "compact_context": compact_context,
                    "original_prediction": original_prediction.to_dict(),
                    "revealed_ground_truth": ground_truth.to_dict(),
                    "framework_prediction_correct": framework_correct,
                    "candidate_judgment_feedback": judgment_feedback,
                    "magnitude_feedback": magnitude_block,
                    "source_catalog": source_index.source_catalog(),
                    **(
                        {"jev_decision_feedback": jev_feedback}
                        if jev_feedback is not None
                        else {}
                    ),
                },
                parser=parse_reflection,
                allow_outcomes=True,
                # Validated enums may equal short ticker aliases such as LOW.
                anonymous_aliases=(),
                sanitize_output_aliases=self.anonymous_aliases,
                max_output_tokens=8_000,
                max_request_tokens=self.request_token_budget,
                patch_corrections=True,
                final_validation_fallback=_reflection_salvage_fallback(
                    source_index, "case", source_identity, item_validator=validate_case_text,
                ),
                repair_resolver=source_index.citation_closure,
            )
            return AgentStep(reflection, usage)
        except CandidateExecutionRejected as exc:
            _emit_runtime_progress(
                getattr(self.caller, "on_progress", None),
                "posthoc_reflection_validation_failed",
                reason=str(exc)[:400],
            )
            correct = original_prediction.is_surge == ground_truth.is_surge and (
                not ground_truth.is_surge
                or original_prediction.magnitude is ground_truth.magnitude
            )
            return AgentStep(
                PredictionSelfReflection(
                    correct=correct,
                    no_findings_reason="posthoc_reflection_validation_failed: " + str(exc),
                    source_identity=source_identity,
                    source_snapshot=source_snapshot,
                ),
                exc.usage,
            )


_FORBIDDEN_ADDITIVE_META_KEYS = frozenset(
    {
        "basic_info_bundle",
        "case_id",
        "company_id",
        "final_context",
        "final_state",
        "identity_aliases",
        "initial_state",
        "prediction_ref",
        "raw_info",
        "trajectories",
    }
)

_REFLECTION_CATEGORIES = {
    "case": (
        "decision_drivers", "why_prediction_failed", "misleading_signals",
        "ignored_evidence", "missing_information", "plan_issues",
    ),
    "plan": (
        "successful_patterns", "failed_patterns", "repeated_failure_modes",
        "misleading_signals", "missing_information_needs", "next_explorations",
    ),
    "round": (
        "successful_patterns", "failed_patterns", "false_positive_patterns",
        "false_negative_patterns", "useful_signals", "suspicious_signals",
        "missing_capabilities", "search_implications",
    ),
}


def _structured_reflection_contract(level: str) -> str:
    """Describe one authored item contract shared by all reflection levels."""

    access = (
        " Inputs are bounded working views, not an exhaustive replay. When "
        "necessary return {\"read_refs\":[\"supplied source_ref or item_ref\"]} "
        "to inspect complete originals, or {\"browse_memory\":{\"cursor\":0,"
        "\"level\":\"case\"}} to discover further briefs (case/plan/round); "
        "optionally add signal_ref for an exact-version associated-Experience index. "
        "Obey memory_access limits and do not infer absence from omitted detail. "
        "Numeric evaluation claims must cite runtime_plan_statistics sources "
        "for each owning Plan, cohort and population; a case reference cannot "
        "support aggregate counts or F1. Aggregate statistic sources have no "
        "individual canonical outcome booleans and cannot be cited inside "
        "outcome_claims. For an aggregate-only observation, use an appropriate "
        "permitted non-outcome category; for a success/failure category, read "
        "actual case outcome sources and cite those canonical claims as well "
        "as the statistics. Never invent a false/true claim for a statistic. "
        "Combined cohort is per Plan, never "
        "pooled round statistics. Research-completed diagnostics exclude "
        "technical cases while official scored metrics retain them. Do not "
        "recompute, pool or change these denominators. Full completion requires "
        "the cited runtime completion rate to be 1. Legacy_statistics_unchecked "
        "items remain readable history, not verified statistical support. "
    ) if level != "case" else ""
    return access + (
        " Return only an object with reflection_items (array) and "
        "selected_reflection_refs (array of supplied lower-level item refs), and "
        "no_findings_reason (null or a specific reason when both arrays are empty). "
        "Each authored item has exactly: category, kind (fact/hypothesis/action), "
        "brief, detail, scope ({case_refs:[], plan_refs:[], conditions:string}), "
        "limitations (string array), source_refs (nonempty supplied-reference "
        "array), counter_refs (supplied-reference array), and outcome_claims "
        "(array of {source_ref, axis:binary|magnitude, correct:boolean}). "
        f"Allowed categories are {list(_REFLECTION_CATEGORIES[level])}. "
        "Runtime supplies IDs, level and evidence status; never author them. "
        "One item makes one main observation, explanation or action. Generate "
        "complete detail and a self-contained actionable brief together: retain "
        "the triggering condition, concrete finding/action and material caveat; "
        "a title or 'improve research' is insufficient. The brief must not add "
        "claims or turn an uncertain explanation into an established rule. "
        "Cite exact supplied source handles. All scope case_refs/plan_refs must "
        "be supported by those sources. Every outcome claim's source_ref must "
        "also appear in that same item's source_refs: list each claim-cited "
        "item in source_refs exactly once. State contrary cases in counter_refs "
        "and limitations. "
        "The scope.conditions must explain when this Experience should be indexed "
        "and used. Limitations must retain known economic/research conditions "
        "weakening, invalidating or reversing its interpretation; do not substitute "
        "missing data checks for those boundaries, and state unknown boundaries "
        "honestly. Inside each authored item, you may additionally return "
        "related_signal_refs: an array of "
        "exact Signal versions present in the supporting source catalog/originals. "
        "Never put related_signal_refs at the top level; the envelope contains "
        "only reflection_items, selected_reflection_refs and no_findings_reason. "
        "These refs index related Experience, not evidence of consumption or effect. "
        "Success/failure assertions require outcome_claims matching the canonical "
        "source facts; technical exclusions cannot be "
        "research successes or failures. "
        + SIGNAL_EXECUTION_STATUS_INSTRUCTION +
        "Category and claim correctness are "
        "linked: successful_patterns and decision_drivers items may carry only "
        "correct=true claims, while failed_patterns, why_prediction_failed, "
        "false_positive_patterns, and false_negative_patterns items may carry "
        "only correct=false claims. A mixed outcome is not a fact error: when "
        "binary direction was right but magnitude was wrong (or the reverse), "
        "author separate items — the correct axis as one success-category "
        "item, the incorrect axis as one failure-category item — instead of "
        "one item whose claims straddle both. Author at most 6 new items in "
        "one response and prefer selecting existing lower-level items by ref; "
        "a complete response with fewer items beats a truncated one. "
        "A realized return does not establish "
        "why it occurred: label causal explanations as hypotheses and propose "
        "a test. Fact briefs/details cannot assert under/overweighting or that "
        "signals/reasons were sufficient to explain or identify the outcome; "
        "record the observed outcome separately from a testable interpretation. "
        "Legacy_inference_unchecked items retain old text and require review; "
        "their source membership and fact tag do not verify the explanation. "
        "Legacy_proof_policy_unchecked actions retain historical text; do not "
        "adopt their mandatory price-proof gate in a new action or Plan. "
        "Source references establish provenance, not correctness. "
        "Opportunity screening does not require a quantified valuation bridge, "
        "stated/concrete price path, threshold-bound projection or guaranteed 2x path. "
        "Do not make a missing forward projection a binding evidence gap that caps "
        "the surge judgment. An authored action may request optional valuation "
        "analysis but cannot make such proof a condition for a positive judgment. "
        "Higher levels act as a sieve: select useful existing items by ref "
        "without rewriting them; author only new sourced comparisons or actions. "
        "Repeated versions of one case do not constitute independent evidence. "
        "Empty arrays are valid when there is no supported additional lesson; "
        "do not invent findings to fill categories."
    )


def _repair_reflection_row(
    raw: Any,
    index: "ReflectionMemoryIndex",
    *,
    level: str,
    owner_ref: str,
    item_validator: Callable[[tuple[Any, ...]], None] | None = None,
) -> Any | None:
    """Mechanically repair one invalid reflection row before dropping it."""

    if not isinstance(raw, Mapping):
        return None
    from stock_opportunity_agent.research.repair import apply_mechanical_repairs

    from stock_opportunity_agent.research.evolution_reflection_memory import (
        _CATEGORIES,
    )

    level_categories = _CATEGORIES.get(level)

    def salvage_parse(package):
        items = index.create_items(
            package["reflection_items"], level=level, owner_ref=owner_ref,
        )
        if item_validator is not None:
            item_validator(items)
        # Keep authored JSON shape, rather than inserting a runtime dataclass
        # into the next full parse and correction snapshot.
        return package["reflection_items"]

    result = apply_mechanical_repairs(
        {"reflection_items": [raw]},
        salvage_parse,
        resolver=index.citation_closure,
        level_categories=level_categories,
    )
    if result is None:
        return None
    items, _ops = result
    return items[0] if items else None


def _reflection_salvage_fallback(
    index: "ReflectionMemoryIndex",
    level: str,
    owner_ref: str,
    *, item_validator: Callable[[tuple[Any, ...]], None] | None = None,
) -> Callable[
    [Mapping[str, Any], ValidationError],
    tuple[dict[str, Any], dict[str, tuple[str, ...]]] | None,
]:
    """Row-level salvage for authored reflection item packages.

    When bounded corrections cannot repair a reflection response, drop only
    the complete invalid ``reflection_items`` rows and reparse, so
    independently valid sibling lessons persist instead of the whole
    package being lost to one bad item. Item refs are content hashes and
    index registration overwrites, so the dry-run validation performed here
    is idempotent with the subsequent full parse of the same rows.
    """

    def salvage(
        failed_output: Mapping[str, Any], failure: ValidationError,
    ) -> tuple[dict[str, Any], dict[str, tuple[str, ...]]] | None:
        raw_items = failed_output.get("reflection_items")
        if not isinstance(raw_items, list) or not raw_items:
            return None
        removed: list[int] = []
        repaired_rows: dict[int, Any] = {}
        for position, raw in enumerate(raw_items):
            try:
                items = index.create_items((raw,), level=level, owner_ref=owner_ref)
                if item_validator is not None:
                    item_validator(items)
            except ValidationError:
                repaired_row = _repair_reflection_row(
                    raw, index, level=level, owner_ref=owner_ref,
                    item_validator=item_validator,
                )
                if repaired_row is not None:
                    repaired_rows[position] = repaired_row
                    continue
                removed.append(position)
        if not removed and not repaired_rows:
            return None
        dropped = set(removed)
        next_output = dict(failed_output)
        remaining = [
            repaired_rows.get(position, raw)
            for position, raw in enumerate(raw_items)
            if position not in dropped
        ]
        next_output["reflection_items"] = remaining
        if remaining:
            next_output["no_findings_reason"] = None
        else:
            next_output["no_findings_reason"] = (
                "reflection_items_all_invalid_salvaged: " + str(failure)[:160]
            )
        return next_output, {
            "removed_paths": tuple(
                f"reflection_items[{position}]" for position in removed
            ),
            "source_substitution_paths": (),
            "context_only_paths": (),
            "normalized_paths": tuple(
                f"reflection_items[{position}]"
                for position in sorted(repaired_rows)
            ),
        }

    return salvage


def _structured_reflection_items(
    value: Mapping[str, Any], *, index: ReflectionMemoryIndex,
    level: str, owner_ref: str,
    item_validator: Callable[[tuple[Any, ...]], None] | None = None,
) -> tuple[tuple[Any, ...], tuple[str, ...], dict[str, Any]]:
    """Validate new authored items and derive the legacy category projection."""

    required = {"reflection_items", "selected_reflection_refs"}
    envelope_issues = [
        ValidationIssue(
            code="reflection_envelope", paths=(field,),
            message=f"Add required reflection field {field}", allowed_repairs=("add",),
        ) for field in sorted(required - set(value))
    ] + [
        ValidationIssue(
            code="reflection_envelope", paths=(field,),
            message=f"Remove unsupported reflection field {field}", allowed_repairs=("remove",),
            repair_context={"invalid_container_paths": [field]}
            if isinstance(value[field], (list, Mapping)) else {},
        ) for field in sorted(set(value) - required - {"no_findings_reason"})
    ]
    raw_items = value.get("reflection_items")
    policy_issues = list(envelope_issues)
    if isinstance(raw_items, list):
        policy_issues.extend(ValidationIssue(
            code="reflection_action_proof_gate", paths=(f"reflection_items[{position}].{field}",),
            allowed_repairs=("replace",),
            message="An action cannot require a quantified/stated price path or threshold-bound projection, or cap/downgrade the judgment solely without that proof; keep such analysis optional.",
        ) for position, item in enumerate(raw_items) if isinstance(item, Mapping) and item.get("kind") == "action"
          for field in ("brief", "detail") if isinstance(item.get(field), str)
          and violates_opportunity_proof_gate(item[field]))
        policy_issues.extend(ValidationIssue(
            code="reflection_fact_inference", paths=(f"reflection_items[{position}].{field}",),
            dependent_paths=(f"reflection_items[{position}].kind",),
            allowed_repairs=("replace",),
            message="Retain the observable fact without weighting/sufficiency inference, or classify the explanation as a testable hypothesis; preserve other items and outcome facts.",
        ) for position, item in enumerate(raw_items) if isinstance(item, Mapping)
          for field in reflection_fact_inference_fields(item))
        for position, item in enumerate(raw_items):
            try:
                index._create_items((item,), level=level, owner_ref=owner_ref, check_inferences=False)
            except ReflectionValidationError as exc:
                prefix = f"reflection_items[{position}]"
                def located(path: str) -> str:
                    return prefix + ("." + path if path else "")
                if any(issue.paths == (located(exc.path),) for issue in policy_issues):
                    continue
                policy_issues.append(ValidationIssue(
                    code="reflection_item", paths=(located(exc.path),), message=str(exc),
                    dependent_paths=tuple(located(path) for path in exc.dependency_paths),
                    allowed_repairs=("replace", "add", "remove"),
                    repair_context={
                        "invalid_container_paths": [located(path) for path in exc.invalid_container_paths],
                        "allowed_append_values": {located(path): values for path, values in exc.allowed_append_values.items()},
                    },
                ))
        if item_validator is not None:
            try:
                item_validator(tuple(raw_items))
            except StructuredValidationError as exc:
                policy_issues.extend(exc.issues)
    if policy_issues:
        raise StructuredValidationError(policy_issues)
    # Retrospective descriptions may discuss probabilities and horizons. They
    # cannot mutate fixed semantics; the eventual Plan proposal is validated at
    # that owning boundary. Applying the Plan instruction word filter here
    # would reject the calibration analysis that this role is asked to provide.
    try:
        items = index.create_items(
            value["reflection_items"], level=level, owner_ref=owner_ref,
        )
    except ReflectionValidationError as exc:
        raise StructuredValidationError((ValidationIssue(
            code="reflection_item", paths=(exc.path,), message=str(exc),
            dependent_paths=exc.dependency_paths,
            allowed_repairs=("replace", "add", "remove"),
            repair_context={
                "invalid_container_paths": list(exc.invalid_container_paths),
                "allowed_append_values": exc.allowed_append_values,
            },
        ),)) from exc
    selected = value["selected_reflection_refs"]
    if not isinstance(selected, list) or any(
        not isinstance(ref, str) for ref in selected
    ):
        raise StructuredValidationError((ValidationIssue(
                code="reflection_selection", paths=("selected_reflection_refs",),
                message="Select only supplied lower-level item references",
            ),))
    if level == "case" and selected:
        raise StructuredValidationError((ValidationIssue(
            code="reflection_selection", paths=("selected_reflection_refs",),
            message="case reflection has no lower-level item to select; return []",
        ),))
    try:
        selected_items = index.select_items(selected)
        levels = {"case": 0, "plan": 1, "round": 2}
        if any(levels[item.level] >= levels[level] for item in selected_items):
            raise ValidationError("Select only strictly lower-level reflection items")
    except ValidationError as exc:
        raise StructuredValidationError((ValidationIssue(
            code="reflection_selection", paths=("selected_reflection_refs",),
            message=str(exc), allowed_repairs=("replace", "remove"),
        ),)) from exc
    categories = _REFLECTION_CATEGORIES[level]
    for position, item in enumerate(items):
        if item.category not in categories:
            raise StructuredValidationError((ValidationIssue(
                    code="reflection_category",
                    paths=(f"reflection_items[{position}].category",),
                    message=f"Allowed categories: {list(categories)}",
                ),))
    projection = {
        category: tuple(item.detail for item in items if item.category == category)
        for category in categories
    }
    reason = value.get("no_findings_reason")
    if reason is not None and (not isinstance(reason, str) or not reason.strip()):
        raise StructuredValidationError((ValidationIssue(
            code="reflection_no_findings", paths=("no_findings_reason",),
            message="no_findings_reason must be null or a nonempty specific reason",
            allowed_repairs=("replace", "remove"),
        ),))
    if not items and not selected and (not isinstance(reason, str) or not reason.strip()):
        raise StructuredValidationError((ValidationIssue(
            code="reflection_no_findings",
            paths=("no_findings_reason", "reflection_items", *(
                ("selected_reflection_refs",) if level != "case" else ()
            )), path_policy="any",
            message="Empty reflection requires a concrete no_findings_reason, or one supported reflection item or allowed lower-level selection",
            allowed_repairs=("add", "replace"),
        ),))
    projection["no_findings_reason"] = reason
    return items, tuple(selected), projection


class _DocumentChannelCaller:
    """Bounded in-loop Raw Info catalog/fetch exchanges for one reflect call.

    Mirrors the proposer's read_refs pattern: the first answers may page the
    catalog, fetch documents or compute (two shared exchanges, at most two
    fetch entries each, no repeats), which the runtime resolves
    through the disclosure interface — point-in-time filtered, journaled by
    the ordinary caller persistence — before the model returns its state.
    """

    _MAX_EXCHANGES = 2
    _MAX_ENTRIES_PER_EXCHANGE = 2

    def __init__(self, caller: JSONRoleCaller, provider: Any) -> None:
        self.caller = caller
        self.provider = provider
        self.exchanges = 0
        self.fetched_keys: set[tuple[str, str | None]] = set()
        self.computed_metric_cards: list[dict[str, Any]] = []
        self.catalog_pages: list[dict[str, Any]] = []
        self.catalog_cursors: set[int] = {0}

    def __getattr__(self, name: str) -> Any:
        return getattr(self.caller, name)

    def complete_json(self, **kwargs: Any) -> tuple[Mapping[str, Any], AgentUsage]:
        usage = AgentUsage()
        payload = dict(kwargs["payload"])
        if kwargs["stage"].endswith("_patch_mechanics_correction"):
            return _complete_json_with_invalid_value(self.caller, **kwargs)
        if not self.catalog_pages:
            self.catalog_pages.append(self.provider.catalog_view())
        payload["document_catalog"] = deepcopy(self.catalog_pages[0])
        if len(self.catalog_pages) > 1:
            payload["document_catalog_pages"] = deepcopy(self.catalog_pages[1:])
        retained_views = getattr(self.provider, "document_views", ())
        if retained_views:
            payload["document_channel"] = deepcopy(list(retained_views))
        if self.computed_metric_cards:
            existing_metrics = list(payload.get("computed_metrics", ()))
            for card in self.computed_metric_cards:
                if card not in existing_metrics:
                    existing_metrics.append(deepcopy(card))
            payload["computed_metrics"] = existing_metrics
        while True:
            request = dict(kwargs)
            request["payload"] = deepcopy(payload)
            if request.get("max_request_tokens") is not None:
                request["max_request_tokens"] = max(
                    0, request["max_request_tokens"] - usage.tokens
                )
            try:
                value, used = _complete_json_with_invalid_value(
                    self.caller, **request
                )
            except (CandidateExecutionRejected, RuntimeBudgetExceeded) as exc:
                exc.usage = usage + exc.usage
                raise
            usage = usage + used
            if set(value) == {"inspect_document_catalog"}:
                query = value["inspect_document_catalog"]
                if (
                    not isinstance(query, Mapping)
                    or set(query) != {"cursor"}
                    or type(query["cursor"]) is not int
                ):
                    raise ValidationError("document catalog request requires one integer cursor")
                cursor = query["cursor"]
                if cursor in self.catalog_cursors:
                    raise ValidationError("document catalog page was already disclosed")
                if self.exchanges >= self._MAX_EXCHANGES:
                    raise ValidationError("document catalog paging exceeds the issued exchange budget")
                page = self.provider.catalog_view(cursor=cursor)
                self.exchanges += 1
                self.catalog_cursors.add(cursor)
                self.catalog_pages.append(page)
                payload["document_catalog_pages"] = deepcopy(self.catalog_pages[1:])
                continue
            if set(value) == {"compute"}:
                entries = value["compute"]
                if self.exchanges >= self._MAX_EXCHANGES:
                    raise ValidationError(
                        "document channel compute exceeds the issued exchange budget"
                    )
                self.exchanges += 1
                cards = self.provider.compute(entries)
                self.computed_metric_cards.extend(deepcopy(cards))
                existing_metrics = list(payload.get("computed_metrics", ()))
                payload["computed_metrics"] = existing_metrics + list(cards)
                continue
            if set(value) != {"fetch_documents"}:
                return value, usage
            entries = value["fetch_documents"]
            if (
                not isinstance(entries, list)
                or not entries
                or len(entries) > self._MAX_ENTRIES_PER_EXCHANGE
                or any(not isinstance(item, Mapping) for item in entries)
            ):
                raise ValidationError(
                    "fetch_documents must be a nonempty array of at most "
                    f"{self._MAX_ENTRIES_PER_EXCHANGE} objects"
                )
            if self.exchanges >= self._MAX_EXCHANGES:
                raise ValidationError(
                    "document channel fetches exceed the issued exchange budget"
                )
            resolved_keys: list[tuple[str, str | None]] = []
            for entry in entries:
                document_id = entry.get("document_id")
                section_id = entry.get("section_id")
                if not isinstance(document_id, str) or not (
                    isinstance(section_id, str) or section_id is None
                ):
                    raise ValidationError(
                        "fetch_documents entries require a document_id and "
                        "optional section_id from the supplied catalog"
                    )
                key = (document_id, section_id)
                if key in self.fetched_keys or key in resolved_keys:
                    raise ValidationError(
                        "document channel entry was already fetched"
                    )
                resolved_keys.append(key)
            self.exchanges += 1
            cards = self.provider.fetch(entries)
            self.fetched_keys.update(resolved_keys)
            existing = list(payload.get("document_channel", ()))
            payload["document_channel"] = existing + list(cards)


class _ReflectionMemoryCaller:
    """Count and audit bounded source reads inside one retrospective role."""

    def __init__(self, caller: JSONRoleCaller, index: ReflectionMemoryIndex, *, role: str, aliases: tuple[str, ...]) -> None:
        self.caller, self.index, self.role, self.aliases = caller, index, role, aliases
        self.disclosures: list[dict[str, Any]] = []
        self.requests: set[str] = set()
        self.read_refs: set[str] = set()

    def __getattr__(self, name: str) -> Any:
        return getattr(self.caller, name)

    def complete_json(self, **kwargs: Any) -> tuple[Mapping[str, Any], AgentUsage]:
        usage = AgentUsage()
        while True:
            request = dict(kwargs)
            request["payload"] = deepcopy(dict(kwargs["payload"]))
            request["payload"]["memory_disclosures"] = deepcopy(self.disclosures)
            request["payload"]["memory_access"] = {
                "remaining_requests": 3 - len(self.requests),
                "total_disclosure_bytes": 48_000,
            }
            if request.get("max_request_tokens") is not None:
                request["max_request_tokens"] = max(0, request["max_request_tokens"] - usage.tokens)
            try:
                value, used = _complete_json_with_invalid_value(self.caller, **request)
            except (CandidateExecutionRejected, RuntimeBudgetExceeded) as exc:
                exc.usage = usage + exc.usage
                raise
            usage = usage + used
            if set(value) not in ({"read_refs"}, {"browse_memory"}):
                return value, usage
            key = _canonical_hash(value)
            try:
                if len(self.requests) >= 3 or key in self.requests:
                    raise ValidationError("reflection memory access is repeated or exceeds three requests")
                remaining = 48_000 - len(json.dumps(self.disclosures, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8"))
                if "read_refs" in value:
                    refs = value["read_refs"]
                    if not isinstance(refs, list) or any(not isinstance(ref, str) for ref in refs):
                        raise ValidationError("read_refs must be an array of supplied references")
                    if self.read_refs.intersection(refs):
                        raise ValidationError("reflection source has already been read")
                    disclosure = self.index.read_refs(refs, role=self.role, max_bytes=remaining)
                    self.read_refs.update(refs)
                else:
                    query = value["browse_memory"]
                    if not isinstance(query, Mapping) or not {"cursor"} <= set(query) or set(query) - {"cursor", "level", "signal_ref"}:
                        raise ValidationError("browse_memory requires cursor and optional level")
                    disclosure = self.index.directory(
                        cursor=query["cursor"], level=query.get("level"),
                        signal_ref=query.get("signal_ref"),
                        max_bytes=min(8_000, remaining),
                    )
                if self.aliases:
                    # The index holds authoritative unmasked originals; the
                    # disclosure served to the model must carry masked content.
                    disclosure = _mask_identity_values(disclosure, self.aliases)
                _validate_additive_meta_payload(disclosure)
                _scan_payload(disclosure, allow_outcomes=True, anonymous_aliases=self.aliases)
                updated = [*self.disclosures, disclosure]
                if len(json.dumps(updated, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")) > 48_000:
                    raise ValidationError("reflection disclosures exceed aggregate byte budget")
                self.disclosures = updated
                self.requests.add(key)
            except ValidationError as exc:
                raise CandidateExecutionRejected(
                    self.role, f"reflection memory access rejected: {exc}", usage=usage,
                ) from exc


def _validate_additive_meta_payload(value: Any, *, path: str = "meta_info") -> None:
    """Keep outcome-aware proposer memory free of identity and source context."""

    if isinstance(value, Mapping):
        for key, nested in value.items():
            normalized = _normalize_field(str(key))
            if normalized in _FORBIDDEN_ADDITIVE_META_KEYS:
                raise ValidationError(
                    f"forbidden context field in proposer meta-info: {path}.{key}"
                )
            _validate_additive_meta_payload(nested, path=f"{path}.{key}")
    elif isinstance(value, (list, tuple)):
        for index, nested in enumerate(value):
            _validate_additive_meta_payload(nested, path=f"{path}[{index}]")


class LLMInformationPlanProposer:
    """Concrete fixed-H_P candidate proposer; it may change only four Plan fields."""

    def __init__(
        self,
        caller: JSONRoleCaller,
        *,
        temperature: float = 1.0,
        available_source_types: Iterable[str] = REGISTERED_SOURCE_TYPE_CATALOG,
    ) -> None:
        if not 0 < temperature <= 1:
            raise ValidationError("Plan proposal temperature must be in (0, 1]")
        self.caller = caller
        self.temperature = temperature
        self.available_source_types = tuple(sorted(set(available_source_types)))
        if not self.available_source_types:
            raise ValidationError("Plan proposer requires available source types")
        self.anonymous_aliases: tuple[str, ...] = ()
        self.request_token_budget: int | None = None
        self.experience_profiles: dict[str, Mapping[str, Any]] = {}

    def set_experience_profiles(self, profiles: Mapping[str, Mapping[str, Any]]) -> None:
        """Freeze runtime performance overlays before this round's proposals."""
        self.experience_profiles = deepcopy(dict(profiles))

    def set_request_token_budget(self, value: int) -> None:
        """Set the exact hard ceiling for one complete proposal request."""

        self.request_token_budget = int(value)

    def set_anonymous_aliases(self, value: Iterable[str]) -> None:
        self.anonymous_aliases = tuple(value)

    def propose(
        self,
        *,
        round_id: int,
        candidate_index: int,
        candidate_count: int,
        proposal_attempt: int,
        forbidden_plan_ids: tuple[str, ...],
        parents: tuple[InformationPlan, ...],
        meta_info: tuple[RoundMetaEntry, ...],
        prior: str,
    ) -> InformationPlan:
        source_entries = [entry.to_model_dict() for entry in meta_info]
        # Build the index from authoritative unmasked entries: item/source refs
        # are content hashes and masking inputs would break ref verification.
        source_index = ReflectionMemoryIndex.from_entries(source_entries,
            performance_profiles=self.experience_profiles)
        meta_payload = source_index.brief_view()
        if self.anonymous_aliases:
            meta_payload = _mask_identity_values(meta_payload, self.anonymous_aliases)
            _scan_payload(
                meta_payload,
                allow_outcomes=True,
                anonymous_aliases=self.anonymous_aliases,
            )
        _validate_additive_meta_payload(meta_payload)
        payload: dict[str, Any] = {
            "fixed_prior": prior,
            "basic_info_orientation_menu": orientation_menu(self.available_source_types),
            "parents": [item.to_dict() for item in parents],
            "meta_info": meta_payload,
            # Snapshot discipline: pin the exact experience-tree view this
            # proposal consumed, so later fitness comparisons can attribute
            # Plans to the memory state that produced them.
            "experience_snapshot_hash": _canonical_hash(meta_payload),
            "available_source_types": list(self.available_source_types),
            "memory_disclosures": [],
            "memory_access": {
                "max_requests": 3,
                "total_disclosure_bytes": 48_000,
                "directory_cursor": 0,
            },
        }
        change_focuses = (
            "Change at least one Basic Info request or H_init instruction while "
            "retaining one compliant market backbone.",
            "Change H_reflect to test a different falsifier, counter-evidence "
            "order, or uncertainty-reduction step.",
            "Change H_analyse to use a different evidence-weighting or decision "
            "rule without changing prediction semantics.",
        )
        payload["proposal_constraints"] = {
            "must_differ_from_every_parent": True,
            "required_change_focus": change_focuses[
                (proposal_attempt - 1) % len(change_focuses)
            ],
        }
        payload["proposal_slot"] = {
            "round_id": round_id,
            "candidate_index": candidate_index,
            "candidate_count": candidate_count,
            "proposal_attempt": proposal_attempt,
        }
        system_prompt = (
            _PREDICTOR_ROLE_AUTHORITY +
            "Apply the fixed H_P prior. When proposing a Plan, return one JSON "
            "object containing B, H_init, H_reflect, H_analyse, and "
            "used_experience_refs as members of that same object. B is an analyst-style source "
            "retrieval plan, not a fixed company profile or computed Signal. "
            "Basic Info composes only the exact versioned action requests in "
            "basic_info_orientation_menu. Copy each selected request_id, description "
            "and source_types verbatim; vary only published integer lookback/count "
            "bounds. Do not author query or coverage fields. Internal fixed recipes "
            "are compiler-owned, not Plan parameters. Select supported actions under "
            "available_source_types rather than requiring every family. "
            "Meta-info is a bounded brief view of committed retrospective memory. "
            "Complete originals remain stored. A brief retains its applicability, "
            "limitations, source handles and validation status; legacy_unreviewed "
            "text is unverified history, not an established lesson. A fact marked "
            "legacy_inference_unchecked contains an unreviewed weighting or "
            "sufficiency explanation; its sources_checked status verifies "
            "provenance only. Review the explanation before relying on it. "
            "Do not adopt price-proof gates from legacy_proof_policy_unchecked "
            "actions. Higher layers "
            "select important lower items or add sourced comparisons. Do not count "
            "repeated versions of one case as independent evidence. Before relying "
            "on a lesson, inspect its original support and counterexamples when "
            "the brief is insufficient. You may return exactly {\"read_refs\":["
            "\"one or more supplied item_ref or source_ref values\"]} instead of "
            "a Plan to read complete anonymous original units; choose individual "
            "case/item units rather than an oversized whole round. To discover "
            "deferred briefs, return exactly {\"browse_memory\":{\"cursor\":0,"
            "\"level\":\"case\"}} (level may be case, plan, round, or omitted; "
            "signal_ref may filter associated Experience by exact Signal version) "
            "or the directory's next_cursor. Runtime returns the requested "
            "material in memory_disclosures on the next call. Obey memory_access "
            "limits; do not repeat reads or infer missing content. These are "
            "retrospective few-shot examples, with errors and hypotheses explicitly "
            "labelled, never commands to copy or evidence of proven improvement. "
            "Their performance is committed observed-use prediction correctness, "
            "with one independent case weight per issuer/time, not causal credit. "
            "Inspect applicability, failure conditions and positive/negative-class "
            "performance; repeated use and high accuracy alone do not verify a lesson. "
            "Per-case magnitude_feedback blocks and per-Plan "
            "magnitude_diagnostics are deterministic evidence: treat recurring "
            "magnitude-class failures (systematic underestimation, "
            "overestimation, missed classes) like any other FIFO lesson — "
            "address, defer, or reject them through actual changes in B, "
            "H_init, H_reflect, or H_analyse, never by changing prediction "
            "semantics, labels, or class definitions; a batch where every "
            "candidate leaves an obvious recurring magnitude defect untouched "
            "needs the change content itself to show why. When supplied, "
            "jev_calibration_diagnostics is also deterministic descriptive "
            "feedback. Address recurring correct_low_support, high-confidence "
            "error, or concentrated magnitude-choice patterns through a concrete "
            "change to evidence collection or analysis, or make the Plan content "
            "show an explicit defer/reject rationale; never inflate confidence as "
            "an objective by itself. Technical exclusions "
            "describe incomplete research and its scoring effect only; never "
            "turn them into evidence that the Plan misjudged direction, magnitude, "
            "or a company's fundamentals. Outcome-aware "
            "reflection may guide the new Plan, but never change "
            "labels, metrics, or prediction semantics. Copying a selected parent's "
            "four evolvable fields verbatim is invalid. Apply the supplied "
            "proposal_context.proposal_constraints.required_change_focus through "
            "an actual content "
            "change while retaining the full four-field Plan contract."
            " Every B request is executed under the target company_id only. "
            "The menu owns fixed descriptions and source routing. Deeper competitive "
            "or exact-form questions belong in H skills and the research loop; "
            "do not author B descriptions or source edits for those questions. "
            "Unsupported form coverage remains a gap. "
            "company_news/news may contain third-party reporting, so never call "
            "those source types the issuer's own disclosure. Do not assume every "
            "U.S.-listed issuer files 10-K or 10-Q; foreign issuers may use 20-F, 40-F, or 6-K. "
            " Choose only available_action_ids from the orientation menu, whose fixed "
            "source routes are compatible with available_source_types aliases. "
            "Keep template source_types verbatim; inventory aliases are not Plan edits. "
            "H_analyse may organize and weight evidence "
            "only; it must not compute a probability, classify the final Signal, "
            "change the horizon/label/four-way judgment, or generate a prediction."
            + _UNTRUSTED_DATA_INSTRUCTION
            + _SOURCE_FACT_RELATION_INSTRUCTION
            + _INFORMATION_PLAN_OUTPUT
            + " Read fixed prior, parents, meta-info, source types, constraints, "
            "and slot metadata from proposal_context. validation_feedback is null "
            "on the initial attempt. When it is an object, correct every field "
            "named by validation_feedback.validation_error using the supplied "
            "invalid_output; preserve every unmentioned request and H_* field "
            "byte-for-byte; returning the same rejected field is not a correction."
            + PATCH_INSTRUCTION
        )
        plan_id = f"plan_r{round_id:04d}_c{candidate_index:02d}"
        parent_ids = tuple(item.plan_id for item in parents)
        parent_content_hashes = {
            _canonical_hash(item.canonical_dict()) for item in parents
        }
        failed_value: Mapping[str, Any] | None = None
        failure: ValidationError | None = None
        read_requests = 0
        disclosed_refs: set[str] = set()
        visible_experience_refs = set(meta_payload["included_refs"])
        browsed_cursors: set[tuple[str | None, int, str | None]] = set()

        def complete_proposal_request(
            stage: str, request_payload: dict[str, Any],
        ) -> Mapping[str, Any]:
            nonlocal read_requests
            while True:
                estimator = getattr(self.caller, "estimate_json_request_tokens", None)
                if self.request_token_budget is not None and callable(estimator):
                    required = estimator(
                        system_prompt=system_prompt, payload=request_payload,
                        allow_outcomes=True, max_output_tokens=4_000,
                        temperature=self.temperature,
                    )
                    if required > self.request_token_budget:
                        raise ExternalBudgetExhausted(
                            "external_request_token_budget_exhausted",
                            "Information Plan proposal working view exceeds frozen "
                            f"request budget: required={required}, limit={self.request_token_budget}",
                        )
                value, _usage = _complete_json_with_invalid_value(
                    self.caller, stage=stage, system_prompt=system_prompt,
                    payload=request_payload, allow_outcomes=True,
                    max_output_tokens=4_000, temperature=self.temperature,
                )
                if set(value) == {"invalid_structured_output", "validation_error"}:
                    from stock_opportunity_agent.research.repair import (
                        complete_truncated_json,
                    )

                    _l0 = complete_truncated_json(
                        str(value["invalid_structured_output"])
                    )
                    if _l0 is not None:
                        try:
                            _candidate = json.loads(_l0[0])
                        except json.JSONDecodeError:
                            _candidate = None
                        if isinstance(_candidate, dict):
                            # Candidate flows into the proposer's own
                            # validation below; the L0 rescue only restores
                            # parseability, the validator stays the arbiter.
                            value = _candidate
                if set(value) not in ({"read_refs"}, {"browse_memory"}):
                    return value
                if read_requests >= 3 or request_payload["validation_feedback"] is not None:
                    raise CandidateProposalRejected("memory read request exceeds the issued access contract")
                disclosures = payload["memory_disclosures"]
                remaining = 48_000 - len(json.dumps(
                    disclosures, ensure_ascii=False, sort_keys=True,
                    separators=(",", ":"),
                ).encode("utf-8"))
                try:
                    if "read_refs" in value:
                        refs = value["read_refs"]
                        if not isinstance(refs, list) or any(not isinstance(ref, str) for ref in refs):
                            raise ValidationError("read_refs must be an array of supplied references")
                        if disclosed_refs.intersection(refs):
                            raise ValidationError("memory reference was already disclosed")
                        disclosure = source_index.read_refs(
                            refs, role="proposer", max_bytes=remaining,
                        )
                        disclosed_refs.update(refs)
                    else:
                        request = value["browse_memory"]
                        if not isinstance(request, Mapping) or not {"cursor"} <= set(request) or set(request) - {"cursor", "level", "signal_ref"}:
                            raise ValidationError("browse_memory requires a directory cursor and optional level")
                        cursor = request["cursor"]
                        level = request.get("level")
                        signal_ref = request.get("signal_ref")
                        if signal_ref is not None and not isinstance(signal_ref, str):
                            raise ValidationError("memory Signal filter requires an exact string ref")
                        if (level is not None and not isinstance(level, str)) or level not in {None, "case", "plan", "round"} or type(cursor) is not int or (level, cursor, signal_ref) in browsed_cursors:
                            raise ValidationError("directory cursor is invalid or already disclosed")
                        disclosure = source_index.directory(cursor=cursor, level=level, signal_ref=signal_ref, max_bytes=min(8_000, remaining))
                        browsed_cursors.add((level, cursor, signal_ref))
                    _validate_additive_meta_payload(disclosure)
                    _scan_payload(disclosure, allow_outcomes=True, anonymous_aliases=self.anonymous_aliases)
                    trial = [*disclosures, disclosure]
                    if len(json.dumps(trial, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")) > 48_000:
                        raise ValidationError("complete memory disclosures exceed aggregate byte budget")
                except ValidationError as exc:
                    raise CandidateProposalRejected(f"memory disclosure rejected: {exc}") from exc
                payload["memory_disclosures"] = trial
                visible_experience_refs.update(item["item_ref"] for item in disclosure.get("items", ()))
                visible_experience_refs.update(source["source_ref"] for source in disclosure.get("sources", ())
                    if source["source_ref"].startswith("reflection:"))
                read_requests += 1
                payload["memory_access"]["remaining_requests"] = 3 - read_requests
        # The proposal attempts share one correction chain so a byte-identical
        # corrected request fails closed instead of replaying the cached
        # rejected response through the exact-response cache.
        with contextlib.ExitStack() as chain_stack:
            chain = getattr(self.caller, "correction_chain", None)
            if callable(chain):
                chain_stack.enter_context(chain(stage="information_plan_propose"))
            for attempt in range(2):
                stage = (
                    "information_plan_propose"
                    if attempt == 0
                    else "information_plan_propose_correction"
                )
                request_payload = {
                    "proposal_context": payload,
                    "validation_feedback": (
                        {
                            "invalid_output": dict(failed_value or {}),
                            "validation_error": str(failure),
                            **_validation_obligations(failure, failed_value),
                        }
                        if attempt
                        else None
                    ),
                }
                patch_contract = None
                if attempt and failed_value and isinstance(failure, StructuredValidationError):
                    patch_contract = state_patch_contract(
                        failed_value, mode="correction",
                        obligations=_validation_obligations(failure, failed_value)["obligations"],
                    )
                    patch_contract["base_location"] = "validation_feedback.invalid_output"
                    request_payload["output_patch_contract"] = patch_contract
                value = complete_proposal_request(stage, request_payload)
                if self.anonymous_aliases:
                    value = _mask_identity_values(value, self.anonymous_aliases)
                    _scan_payload(
                        value,
                        allow_outcomes=True,
                        anonymous_aliases=self.anonymous_aliases,
                    )
                try:
                    if set(value) == {"invalid_structured_output", "validation_error"}:
                        raise ValidationError(str(value["validation_error"]))
                    if patch_contract is not None:
                        value = apply_state_patch(failed_value, value, contract=patch_contract)
                    if attempt and failed_value and failure is not None:
                        obligations = _validation_obligations(failure, failed_value)
                        authorized_paths = ([entry["path"] for entry in patch_contract["allowed_operations"]]
                            if patch_contract is not None else [
                            path
                            for obligation in obligations["obligations"]
                            for path in obligation["must_change_paths"]
                            if path.startswith(
                                ("B.", "B[", "H_init", "H_reflect", "H_analyse")
                            )
                        ])
                        if authorized_paths:
                            drift_paths = _scoped_correction_drift_paths(
                                failed_value,
                                value,
                                authorized_paths,
                            )
                            if drift_paths:
                                raise ValidationError(
                                    "information_plan_propose correction changed "
                                    "unrelated valid content outside "
                                    f"authorized_paths={authorized_paths}, "
                                    f"unrelated_changed_paths={drift_paths}. Preserve "
                                    "every unrelated B request and H_* field "
                                    "byte-for-byte"
                                )
                    from stock_opportunity_agent.research.repair import mechanical_repair_candidate

                    value, repair_ops = mechanical_repair_candidate(value)
                    if repair_ops:
                        _emit_runtime_progress(
                            getattr(self.caller, "on_progress", None),
                            "mechanical_repair_progress", stage=stage,
                            repairs=[op.__dict__ for op in repair_ops],
                        )
                    _validate_raw_information_plan_request_fields(value)
                    normalized = _normalize_information_plan_output(
                        value,
                        plan_id=plan_id,
                        parent_ids=parent_ids,
                    )
                    adoption_issues: list[ValidationIssue] = []
                    if "used_experience_refs" in value:
                        adopted = value["used_experience_refs"]
                        if (not isinstance(adopted, list) or len(adopted) > 48
                            or any(not isinstance(ref, str) or ref not in visible_experience_refs for ref in adopted)
                            or len(set(adopted)) != len(adopted)):
                            raise StructuredValidationError((ValidationIssue(
                                code="experience_adoption_invalid", paths=("used_experience_refs",),
                                allowed_repairs=("replace",),
                                message="used_experience_refs must contain only unique actually disclosed item refs; [] means no adoption",
                            ),))
                        normalized["experience_usage"] = {
                            "snapshot_hash": _canonical_hash({"brief": meta_payload,
                                "disclosures": payload["memory_disclosures"]}),
                            "item_refs": adopted,
                        }
                    else:
                        adoption_issues.append(ValidationIssue(
                            code="experience_adoption_missing", paths=("used_experience_refs",),
                            allowed_repairs=("add",),
                            message=("New proposal output requires used_experience_refs: "
                                "add only actually adopted disclosed refs, or [] for no adoption. "
                                "Missing metadata is unknown, not an empty adoption list; "
                                "preserve B and every H_* field"),
                        ))
                    validate_raw_orientation_policy(normalized.get("B", normalized.get("basic_info_policy", {})))
                    plan = _parse_role_output(
                        stage, normalized, InformationPlan.from_dict
                    )
                    try:
                        _validate_plan_for_proposer_context(
                            plan, available_source_types=self.available_source_types,
                        )
                    except StructuredValidationError as exc:
                        raise StructuredValidationError([*adoption_issues, *exc.issues]) from exc
                    if adoption_issues:
                        raise StructuredValidationError(adoption_issues)
                    if _canonical_hash(plan.canonical_dict()) in parent_content_hashes:
                        raise _proposal_focus_issue(proposal_attempt, "candidate Plan exactly duplicates a selected parent")
                    try:
                        _validate_proposal_change_focus(
                            plan, parents,
                            focus_index=(proposal_attempt - 1) % len(change_focuses),
                        )
                    except ValidationError as exc:
                        raise _proposal_focus_issue(proposal_attempt, str(exc)) from exc
                    return plan
                except ValidationError as exc:
                    if not isinstance(exc, StructuredValidationError) and set(value) != {
                        "invalid_structured_output", "validation_error",
                    }:
                        raise CandidateProposalRejected(
                            "information_plan_propose has no typed local repair authority: "
                            + str(exc)
                        ) from exc
                    failed_value = value
                    failure = exc
        raise CandidateProposalRejected(
            f"information_plan_propose rejected after one correction: {failure}"
        )


def _proposal_focus_issue(attempt: int, reason: str) -> StructuredValidationError:
    """Authorize only the evolvable components required by the issued focus."""

    paths = (("B.requests", "H_init"), ("H_reflect",), ("H_analyse",))[(attempt - 1) % 3]
    return StructuredValidationError((ValidationIssue(
        code="proposal_change_focus", paths=paths, path_policy="any",
        allowed_repairs=("replace", "add", "remove"),
        message=reason + "; apply proposal_constraints.required_change_focus",
    ),))


def _need_disposition_evolution(item: Any) -> list[dict[str, Any]]:
    """Retain accepted scope provenance without inventing legacy decisions."""

    return [
        {"round": delta.get("round"),
         "need_dispositions": deepcopy(delta["need_dispositions"])}
        for delta in getattr(item, "state_deltas", ())
        if isinstance(delta, Mapping) and "need_dispositions" in delta
    ]


def _plan_critic_trajectory(
    item: Any,
    *,
    case_index: int,
) -> dict[str, Any]:
    """Return the outcome-aware critic view without repeated source context."""

    for round_row in getattr(item, "signal_rounds", ()):
        for result in round_row.batch.results:
            require_signal_result_pit(result, as_of=item.prediction_time)
    if is_technical_exclusion_trajectory(item):
        return {
            "case_index": case_index,
            "state_evolution": _need_disposition_evolution(item),
            "stop_reason": item.stop_reason.value,
            "termination_trigger": (
                item.termination_trigger.value
                if item.termination_trigger is not None
                else None
            ),
            "technical_exclusion": {
                "failure_class": "bounded_structured_correction_exhaustion",
                "scoring_effect": (
                    "false_negative"
                    if item.ground_truth.is_surge
                    else "technical_negative_abstention_not_true_negative"
                ),
                "research_attribution_allowed": False,
            },
        }
    data = dict(item.to_dict())
    final = data.get("final_context", {})
    basic = final.get("basic_info", {}) if isinstance(final, Mapping) else {}
    if not isinstance(basic, Mapping) or not isinstance(basic.get("source_index"), list):
        basic = data.get("basic_info_bundle", {})
    compact: dict[str, Any] = {"case_index": case_index,
        "basic_info_source_index": basic_info_source_index(basic, upstream=data.get("basic_info_bundle")) if isinstance(basic, Mapping) else []}
    for key in (
        "stop_reason",
        "termination_trigger",
        "prediction",
        "ground_truth",
        "candidate_judgment_feedback",
        "jev_decision_feedback",
        "self_reflection",
    ):
        if key in data:
            compact[key] = data[key]
    prediction_object = getattr(item, "prediction", None)
    truth_object = getattr(item, "ground_truth", None)
    if prediction_object is not None and truth_object is not None:
        compact["magnitude_feedback"] = magnitude_feedback(
            prediction_object,
            truth_object,
        )

    compact_rounds: list[dict[str, Any]] = []
    for round_value in data.get("signal_rounds", ()):
        if not isinstance(round_value, Mapping):
            continue
        batch = round_value.get("batch", {})
        raw_results = batch.get("results", ()) if isinstance(batch, Mapping) else ()
        signal_results: list[dict[str, Any]] = []
        for result in raw_results:
            if not isinstance(result, Mapping):
                continue
            model_result = signal_result_model_view(result, as_of=item.prediction_time)
            compact_result = {
                key: model_result[key]
                for key in (
                    "signal_id",
                    "version",
                    "state",
                    "interpretation",
                    "status",
                    "execution",
                )
                if key in model_result
            }
            evidence = model_result.get("evidence")
            if isinstance(evidence, Mapping):
                compact_result["evidence_counts"] = {
                    key: len(value) if isinstance(value, list) else 0
                    for key in ("supporting", "counter")
                    for value in (evidence.get(key),)
                }
            signal_results.append(compact_result)
        compact_round = {
            "information_needs": list(round_value.get("information_needs", ())),
            "selected_signals": list(round_value.get("selected_signals", ())),
            "selections": [
                dict(item)
                for item in round_value.get("selections", ())
                if isinstance(item, Mapping)
            ],
            "signal_results": signal_results,
        }
        if "jev_routing_decisions" in round_value:
            compact_round["jev_routing_decisions"] = [
                dict(item)
                for item in round_value.get("jev_routing_decisions", ())
                if isinstance(item, Mapping)
            ]
        compact_rounds.append(compact_round)
    compact["signal_rounds"] = compact_rounds
    compact["state_evolution"] = _need_disposition_evolution(item)
    return compact


def _round_reflection_record(record: PlanRecord) -> dict[str, Any]:
    """Compact one record without trajectories, identities, or per-case labels."""

    evaluation = record.evaluation
    fitness = record.fitness
    value = {
        "plan_id": record.plan_id,
        "parent_ids": list(record.plan.parent_ids),
        "round_id": record.round_id,
        "plan": record.plan.to_dict(),
        "metrics": record.metrics.to_dict(),
        "reflection": record.reflection.to_dict(),
        "signal_usage": {
            ref: dict(counts) for ref, counts in record.signal_usage.items()
        },
        "fitness": fitness.to_dict(),
        "evaluation": {
            "evaluation_stage": evaluation.evaluation_stage,
            "n_cases": evaluation.n_cases,
            "dataset_snapshot_ids": list(evaluation.dataset_snapshot_ids),
            "metrics_by_cohort": {
                cohort: metrics.to_dict()
                for cohort, metrics in evaluation.metrics_by_cohort.items()
            },
        },
    }
    record_trajectories = getattr(record, "trajectories", None)
    if record_trajectories:
        value["magnitude_diagnostics"] = research_magnitude_diagnostics(
            record_trajectories
        )
        calibration = research_jev_calibration_diagnostics(record_trajectories)
        if calibration is not None:
            value["jev_calibration_diagnostics"] = calibration
        value["technical_completion"] = technical_completion_diagnostics(
            record_trajectories
        )
    return value


class LLMPlanCritic:
    """Plan-level critic over the complete saved validation batch."""

    def __init__(self, caller: JSONRoleCaller) -> None:
        self.caller = caller
        self.anonymous_aliases: tuple[str, ...] = ()

    def set_anonymous_aliases(self, value: Iterable[str]) -> None:
        self.anonymous_aliases = tuple(value)

    def critique(
        self,
        *,
        plan: InformationPlan,
        trajectories: tuple[Any, ...],
        metrics: PlanMetrics,
        parent_comparisons: tuple[Mapping[str, Any], ...] = (),
    ) -> PlanReflection:
        try:
            payload = {
                "plan": plan.to_dict(),
                "metrics": metrics.to_dict(),
                "parent_comparisons": [dict(item) for item in parent_comparisons],
                "trajectories": [
                    _plan_critic_trajectory(item, case_index=index)
                    for index, item in enumerate(trajectories, start=1)
                ],
            }
            if trajectories and all(
                getattr(item, "prediction", None) is not None
                and getattr(item, "ground_truth", None) is not None
                for item in trajectories
            ):
                payload["magnitude_diagnostics"] = research_magnitude_diagnostics(
                    trajectories
                )
                calibration = research_jev_calibration_diagnostics(trajectories)
                if calibration is not None:
                    payload["jev_calibration_diagnostics"] = calibration
                payload["technical_completion"] = technical_completion_diagnostics(
                    trajectories
                )
            if self.anonymous_aliases:
                payload = _mask_identity_values(payload, self.anonymous_aliases)
                _scan_payload(
                    payload,
                    allow_outcomes=True,
                    anonymous_aliases=self.anonymous_aliases,
                )
            owner_ref = "reflection_plan:" + _canonical_hash(plan.canonical_dict())
            source_rows = [
                CaseReflectionEvidence.from_trajectory(item, case_index=position).to_model_dict()
                for position, item in enumerate(trajectories, start=1)
            ]
            # Authoritative unmasked index keeps item/source refs verifiable;
            # identity is removed only from the model-facing payload below.
            source_index = ReflectionMemoryIndex.from_case_rows(
                source_rows, owner_ref=owner_ref,
            )
            source_index.register_plan_statistics(
                payload, plan_ref=owner_ref, plan_id=plan.plan_id,
            )
            catalog = source_index.catalog_view()
            briefs = source_index.brief_view()
            trajectories_view = [
                {**{key: row[key] for key in (
                    "case_index", "stop_reason", "termination_trigger",
                    "technical_exclusion", "candidate_judgment_feedback", "magnitude_feedback",
                    "recorded_signal_execution_failures",
                ) if key in row},
                 "state_evolution": _need_disposition_evolution(trajectory),
                 "basic_info_source_index": summary.get("basic_info_source_index", [])}
                for row, trajectory, summary in zip(source_rows, trajectories, payload["trajectories"], strict=True)
            ]
            if self.anonymous_aliases:
                catalog = _mask_identity_values(catalog, self.anonymous_aliases)
                briefs = _mask_identity_values(briefs, self.anonymous_aliases)
                trajectories_view = _mask_identity_values(
                    trajectories_view, self.anonymous_aliases
                )
            trajectories_view, visibility_profiles = pack_critic_visibility(trajectories_view)
            payload["source_catalog"] = catalog["sources"]
            payload["source_coverage"] = catalog["counts"]
            payload["reflection_briefs"] = briefs
            payload["trajectories"] = trajectories_view
            payload["basic_info_visibility_profiles"] = visibility_profiles

            def parse_reflection(value: Mapping[str, Any]) -> PlanReflection:
                items, selected, projection = _structured_reflection_items(
                    value, index=source_index, level="plan", owner_ref=owner_ref,
                )
                return PlanReflection(
                    **projection, reflection_items=items,
                    selected_reflection_refs=selected,
                )

            reflection, _usage = _complete_parsed_role(
                _ReflectionMemoryCaller(
                    self.caller, source_index, role="plan_critic",
                    aliases=self.anonymous_aliases,
                ),
                stage="plan_critic",
                system_prompt=(
                    _PREDICTOR_ROLE_AUTHORITY +
                    "Each trajectories.basic_info_source_index row combines its profile_ref descriptor "
                    "from basic_info_visibility_profiles with its complete projection_ids. Read both "
                    "as one visibility row. Profiles are local to this payload; null means unknown, "
                    "and markers are discovery hints, not citable evidence or reflection source refs. "
                    "Ground reflection in this batch's deterministic outcome "
                    "diagnostics and sourced briefs. Read registered original case "
                    "reflections when post-hoc detail and its canonical outcome "
                    "feedback are needed to support an observation. "
                    "state_evolution records actual accepted need dispositions; "
                    "Routing's expected answer scope does not establish completion. "
                    "Distinguish unanswered and partial needs from full answers, "
                    "and treat authored disposition reasons as claims to review. "
                    "Return only the vertical cross-case and parent-child layer: the "
                    "runtime preserves every original post-hoc case reflection "
                    "separately, so do not rewrite it or present this output as its "
                    "replacement. Separate binary-direction failures from "
                    "magnitude-class failures: use the per-case magnitude_feedback "
                    "error kinds and the magnitude_diagnostics matrix, supports, and "
                    "conditional accuracy to state whether the Plan mislabels "
                    "direction, underestimates class, overestimates class, or "
                    "concentrates error in one support-poor class, and weigh that "
                    "against the binary tradeoff before proposing changes. Treat "
                    "jev_calibration_diagnostics as deterministic descriptive "
                    "feedback: explain correct_low_support cases, high-confidence "
                    "errors, and concentrated magnitude choices, and connect any "
                    "recurring defect to a concrete Plan change or an explicit "
                    "defer/reject rationale. Do not optimize confidence upward in "
                    "isolation; better feedback means lower Brier/log loss and "
                    "better class discrimination on frozen cases. Treat "
                    "four-way feedback and magnitude diagnostics as reflection "
                    "evidence about what failed; Combined Binary F1 remains the "
                    "primary fitness and parent-selection score, with magnitude "
                    "macro-F1 as the confirmed secondary ordering applied only at "
                    "exactly equal Combined Binary F1. Technical exclusions remain "
                    "inside the frozen score denominator, but are incomplete research: "
                    "report their completion and scoring effects separately and never "
                    "attribute their synthetic abstentions to Plan research quality. "
                    "Use parent_comparisons to identify structural regressions or "
                    "improvements. A metric_delta is valid only when "
                    "same_evaluation_snapshot is true; otherwise compare Plan "
                    "structure without claiming a causal metric effect. These "
                    "comparisons are reflection evidence only."
                    + _UNTRUSTED_DATA_INSTRUCTION
                    + _SOURCE_FACT_RELATION_INSTRUCTION
                    + _structured_reflection_contract("plan")
                ),
                payload=payload,
                parser=parse_reflection,
                allow_outcomes=True,
                anonymous_aliases=self.anonymous_aliases,
                sanitize_output_aliases=self.anonymous_aliases,
                max_output_tokens=8_000,
                patch_corrections=True,
                final_validation_fallback=_reflection_salvage_fallback(
                    source_index, "plan", owner_ref,
                ),
                repair_resolver=source_index.citation_closure,
            )
            return reflection
        except CandidateExecutionRejected as exc:
            _emit_runtime_progress(
                getattr(self.caller, "on_progress", None),
                "plan_critic_validation_failed",
                reason=str(exc)[:400],
            )
            return PlanReflection(
                no_findings_reason="plan_critic_validation_failed: " + str(exc),
            )


class LLMRoundReflector:
    """Concrete fixed-H_R reflector over newly completed round records only."""

    def __init__(self, caller: JSONRoleCaller) -> None:
        self.caller = caller
        self.anonymous_aliases: tuple[str, ...] = ()

    def set_anonymous_aliases(self, value: Iterable[str]) -> None:
        self.anonymous_aliases = tuple(value)

    def reflect(
        self,
        *,
        round_id: int,
        records: tuple[PlanRecord, ...],
        prior: str,
        parent_comparisons_by_plan_id: Mapping[
            str, tuple[Mapping[str, Any], ...]
        ] | None = None,
    ) -> RoundMetaEntry:
        comparisons = parent_comparisons_by_plan_id or {}
        expected_plan_ids = {record.plan_id for record in records}
        if set(comparisons) - expected_plan_ids:
            raise ValidationError(
                "round reflection parent comparisons cite an unknown Plan"
            )
        if len(records) < 2:
            # Visible skip: a single complete Plan carries no horizontal
            # cross-Plan insight, but the skip must be distinguishable from
            # "the model found nothing" in downstream learning audits.
            return RoundMetaEntry(
                round_id=round_id,
                no_findings_reason=(
                    "round_reflection_skipped_single_complete_plan"
                ),
                evidence_refs=tuple(record.plan_id for record in records),
            )
        try:
            payload = {
                "round_id": round_id,
                "fixed_prior": prior,
                "records": [_round_reflection_record(item) for item in records],
                "parent_comparisons_by_plan_id": {
                    plan_id: [dict(item) for item in comparisons[plan_id]]
                    for plan_id in sorted(comparisons)
                },
            }
            source_rows = [
                PlanMetaReflection.from_record(
                    record, parent_comparisons=comparisons.get(record.plan_id, ()),
                ).to_model_dict()
                for record in records
            ]
            # Authoritative unmasked index; the whole payload is masked at
            # egress below before it reaches the model.
            owner_ref = "reflection_round:" + _canonical_hash(source_rows)
            source_index = ReflectionMemoryIndex.from_plan_rows(
                source_rows, owner_ref=owner_ref,
            )
            catalog = source_index.catalog_view()
            payload["source_catalog"] = catalog["sources"]
            payload["source_coverage"] = catalog["counts"]
            payload["reflection_briefs"] = source_index.brief_view()
            for record_view in payload["records"]:
                record_view.pop("reflection", None)

            def parse_reflection(value: Mapping[str, Any]) -> RoundMetaEntry:
                items, selected, projection = _structured_reflection_items(
                    value, index=source_index, level="round", owner_ref=owner_ref,
                )
                return RoundMetaEntry(
                    round_id=round_id, **projection,
                    evidence_refs=tuple(record.plan_id for record in records),
                    reflection_items=items, selected_reflection_refs=selected,
                )

            if self.anonymous_aliases:
                payload = _mask_identity_values(payload, self.anonymous_aliases)
                _scan_payload(
                    payload,
                    allow_outcomes=True,
                    anonymous_aliases=self.anonymous_aliases,
                )
            reflection, _usage = _complete_parsed_role(
                _ReflectionMemoryCaller(
                    self.caller, source_index, role="round_reflector",
                    aliases=self.anonymous_aliases,
                ),
                stage="round_reflect",
                system_prompt=(
                    "Apply fixed H_R only to these new records; runtime owns round "
                    "and Plan identities. Return only horizontal insight across the newly "
                    "sampled child Plans. The runtime separately preserves original case "
                    "reflections and exact vertical Plan reflections; do not rewrite or "
                    "replace those layers. Use the per-record magnitude_diagnostics to "
                    "add horizontal insight about recurring magnitude-class failures "
                    "(systematic underestimation, overestimation, or support-poor "
                    "classes) alongside binary patterns. Use parent comparisons to "
                    "identify structural regressions or improvements. A metric_delta "
                    "is valid only when same_evaluation_snapshot is true; otherwise "
                    "compare Plan structure without claiming a causal metric effect. "
                    "Parent comparisons are reflection evidence only; Combined "
                    "Binary F1 remains the primary fitness and parent-selection "
                    "score, with magnitude macro-F1 as the confirmed secondary "
                    "ordering applied only at exactly equal Combined Binary F1. "
                    "Technical exclusions remain scored but are not research "
                    "outcomes: use technical_completion only for completion and "
                    "scoring-impact reporting, never for Plan or magnitude lessons."
                    + _UNTRUSTED_DATA_INSTRUCTION
                    + _SOURCE_FACT_RELATION_INSTRUCTION
                    + _structured_reflection_contract("round")
                ),
                payload=payload,
                parser=parse_reflection,
                allow_outcomes=True,
                anonymous_aliases=self.anonymous_aliases,
                sanitize_output_aliases=self.anonymous_aliases,
                max_output_tokens=8_000,
                patch_corrections=True,
                final_validation_fallback=_reflection_salvage_fallback(
                    source_index, "round", owner_ref,
                ),
                repair_resolver=source_index.citation_closure,
            )
            return reflection
        except CandidateExecutionRejected as exc:
            _emit_runtime_progress(
                getattr(self.caller, "on_progress", None),
                "round_reflection_validation_failed",
                reason=str(exc)[:400],
            )
            return RoundMetaEntry(
                round_id=round_id,
                no_findings_reason="round_reflection_validation_failed: " + str(exc),
                evidence_refs=tuple(record.plan_id for record in records),
            )
