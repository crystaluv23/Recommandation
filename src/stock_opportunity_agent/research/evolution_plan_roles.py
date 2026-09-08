"""Research, routing, prediction, and Plan model-role adapters."""

from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from typing import Any, Iterable, Mapping
from stock_opportunity_agent.artifacts import canonical_json_hash as _canonical_hash
from stock_opportunity_agent.research.evolution_dataset import _add_months
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
    GroundTruth,
    InformationPlan,
    PlanMetrics,
    PlanMetaMemory,
    PlanRecord,
    PlanReflection,
    PredictionSelfReflection,
    ResearchState,
    ResearchEvidenceRef,
    RoundMetaEntry,
    SignalSelectionDecision,
    candidate_judgment_feedback,
    _mask_identity_values,
)
from stock_opportunity_agent.signal_library import (
    FrozenSignalRegistry,
    SignalBatchResult,
    SignalResult,
    SignalSpec,
    SIGNAL_CONTEXT_TAGS,
    signal_result_model_view,
)
from stock_opportunity_agent.research.evolution_settings import (
    REGISTERED_SOURCE_TYPE_CATALOG,
)
from stock_opportunity_agent.research.evolution_transport import (
    JSONRoleCaller,
    _complete_json_with_invalid_value,
    _normalize_field,
    _scan_payload,
)
from stock_opportunity_agent.research.evolution_output_validation import (
    _BLIND_PREDICTION_OUTPUT,
    _INFORMATION_PLAN_OUTPUT,
    _PLAN_REFLECTION_OUTPUT,
    _PREDICTION_REFLECTION_OUTPUT,
    _REFLECT_RESEARCH_STATE_OUTPUT,
    _RESEARCH_STATE_CORRECTION_GUIDANCE,
    _RESEARCH_STATE_OUTPUT,
    _ROUND_META_OUTPUT,
    _UNTRUSTED_DATA_INSTRUCTION,
    _blind_prediction_with_baseline,
    _compact_posthoc_context,
    _complete_parsed_role,
    _indexed_row_quarantine_fallback,
    _parse_role_output,
    _prediction_reflection_from_role,
    _reject_fixed_semantics_redefinition,
    _research_state_evidence_grounding_fallback,
    _scoped_correction_drift_paths,
    _validate_fixed_plan_semantics,
    _validate_proposal_change_focus,
    _validate_proposed_market_backbone,
    _validate_proposed_plan_skills,
    _validate_proposed_request_scope,
    _validation_obligations,
)
from stock_opportunity_agent.research.evolution_research_validation import (
    _coordinated_residual_facet_terms,
    _normalize_information_plan_output,
    _normalize_research_state_output,
    _normalized_need_content_tokens,
    _reflection_need_transition_contract,
    _reflection_selection_intents,
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
        self.evaluation_context: dict[str, str] | None = None
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
        state, usage = _complete_parsed_role(
            self.caller,
            stage="research_controller_initialize",
            system_prompt=(
                "Apply H_init to Basic Info only. Return one ResearchState JSON object; "
                "information needs must be natural language, not Signal ids. The fixed "
                "six-month adjusted-share-price doubling outcome is the evaluation "
                "definition, not an issuer statement or target. Ask only for "
                "issuer-specific evidence bearing on its feasibility; never ask for "
                "the terms, definition, baseline date, or baseline price of the "
                "evaluation outcome; runtime owns those inputs. A future operating "
                "event outside the six-month horizon may matter through expectation "
                "repricing, but do not condition the six-month outcome on that later "
                "event already having occurred; name the within-horizon evidence or "
                "milestone that could change expectations instead. "
                "evaluation_context is runtime-owned control, not source evidence; "
                "use its prediction_time and horizon_end to enforce that boundary. "
                "Every next_information_needs item must request evidence that could "
                "already exist by prediction_time. Do not ask for the contents, "
                "results, or metrics of a report, release, filing, or announcement "
                "published after prediction_time. You may ask what was already "
                "disclosed by prediction_time about a scheduled future catalyst, "
                "milestone, expectation, or timeline. "
                "Every "
                "next_information_needs item must contain only facts absent from "
                "Basic Info and from the evidence or beliefs you return. Do not ask "
                "again for an already visible fact; when a compound question is "
                "partly answered, ask only its unresolved facets. A request's status "
                "describes source resolution while projection_status describes what "
                "you can actually see. partial_context_budget, "
                "omitted_context_budget, and no_context_spans are not evidence that "
                "the requested fact is absent; keep a decision-relevant omitted "
                "facet unresolved instead of asserting absence."
                " The downstream Predictor receives this compact ResearchState, not "
                "the complete Basic projection text. Keep the smallest material "
                "direct expectation support or counter-evidence visible in Basic "
                "Info, such as a price target, management guidance, or issuer "
                "catalyst, when it bears on the fixed outcome; do not enumerate "
                "every request or source."
                + _UNTRUSTED_DATA_INSTRUCTION
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
                    )
                ),
                phase="initialize",
                basic_info=basic_info,
            ),
            allow_outcomes=False,
            max_output_tokens=2_000,
            max_request_tokens=self.request_token_budget,
            stable_correction_prefix=True,
            correction_guidance=_RESEARCH_STATE_CORRECTION_GUIDANCE,
            enforce_scoped_correction=True,
            exact_compaction_scope=True,
            final_validation_fallback=_research_state_evidence_grounding_fallback,
        )
        return AgentStep(state, usage)

    def reflect(
        self,
        plan: InformationPlan,
        state: ResearchState,
        batch: SignalBatchResult,
    ) -> AgentStep[ResearchState]:
        selections = self.reflection_selections
        must_finalize = self.reflection_must_finalize
        termination_trigger = self.reflection_termination_trigger
        self.reflection_selections = ()
        self.reflection_must_finalize = False
        self.reflection_termination_trigger = None
        reflected, usage = _complete_parsed_role(
            self.caller,
            stage="research_controller_reflect",
            system_prompt=(
                "Apply H_reflect once to the complete Signal batch. Return one "
                "ResearchState JSON object with continue/finalize decision. Retain "
                "the provenance fields of prior Basic Info evidence refs byte-for-byte; "
                "the claim may be restated. For retained Basic refs, copy exactly "
                "kind, claim, projection_id, and exact_text from the indexed "
                "research_state.supporting_evidence item, changing only claim if needed. "
                "A new Signal evidence ref must use "
                "kind=signal, a signal_ref from the current batch, "
                "evidence_group=supporting or counter, and the zero-based evidence_index. "
                "Use only an exact tuple listed by signal_evidence_ref_catalog. Every "
                "numeric quantity in a new Signal claim must occur in the union of the "
                "model_evidence_text items referenced by refs with that same claim; "
                "runtime revalidates it against complete canonical evidence. "
                "For a deterministic Signal row with exact_claim_if_adopted, if you "
                "cite that result, copy the field byte-for-byte into the evidence "
                "claim and every quantitative belief; do not round it, convert it "
                "to a percentage, or add approximate raw values. "
                "Copy a retained Signal ref's prior claim byte-for-byte because its "
                "backing batch is no longer visible. If you adopt new current-batch "
                "Signal evidence and continue, narrow or replace answered information "
                "needs and update resolved/open questions. Keep a need byte-for-byte "
                "when the batch did not answer it; do not change text merely to show "
                "motion. Embedding the full old need inside a longer sentence is "
                "invalid, and a newly resolved question cannot coexist with an exact "
                "retained same-topic need. Use need_transition_contract as the sole "
                "need-ownership map. Each need_rules row names the exact prior need, "
                "available direct-answer actions, unavailable direct-answer refs, and "
                "context-only refs. Only when you adopt evidence from one listed "
                "available answer action may you change that exact need. For a full "
                "action remove the exact need; for a partial action replace it with "
                "the action's residual_need byte-for-byte. Every rule marked "
                "preserve_exactly, and every conditional "
                "rule whose available answer evidence you did not adopt, must retain "
                "its need byte-for-byte. Unavailable and context-only refs never "
                "authorize changing a need. "
                "Deleting another need or returning the targeted need unchanged is "
                "invalid. Use research_state_capacity as an exact admission budget: "
                "do not add more items to any field or to the combined state than its "
                "new_item_capacity, and compact existing items first when capacity is "
                "zero. If reflection_runtime.must_finalize is true, this is the "
                "last executable evidence batch: return decision=finalize based only "
                "on accepted evidence, while preserving unresolved uncertainty in "
                "open_questions or next_information_needs. If every current-batch "
                "Signal is unavailable, preserve every prior ResearchState field and "
                "item byte-for-byte and change only decision to finalize. An "
                "unavailable Signal is only a coverage diagnostic: it is "
                "not evidence of absence and cannot create a belief or resolve a question."
                + _UNTRUSTED_DATA_INSTRUCTION
                + _REFLECT_RESEARCH_STATE_OUTPUT
            ),
            payload={
                "reflection_skill": plan.reflection_skill,
                "research_state": state.to_dict(),
                "signal_batch": _signal_batch_model_view(batch),
                "signal_evidence_ref_catalog": _signal_evidence_ref_catalog(batch),
                "executed_selection_intents": _reflection_selection_intents(
                    selections
                ),
                "need_transition_contract": _reflection_need_transition_contract(
                    state,
                    selections,
                    batch,
                ),
                "research_state_capacity": _research_state_capacity(state),
                "reflection_runtime": {
                    "must_finalize": must_finalize,
                    "termination_trigger": (
                        termination_trigger.value if termination_trigger else None
                    ),
                },
            },
            parser=lambda value: _validate_research_state_refs(
                ResearchState.from_dict(
                    _normalize_research_state_output(
                        value,
                        previous_state=state,
                    )
                ),
                phase="reflect",
                previous_state=state,
                batch=batch,
                selections=selections,
                must_finalize=must_finalize,
            ),
            allow_outcomes=False,
            max_output_tokens=2_000,
            max_request_tokens=self.request_token_budget,
            stable_correction_prefix=True,
            correction_guidance=_RESEARCH_STATE_CORRECTION_GUIDANCE,
            enforce_scoped_correction=True,
            exact_compaction_scope=True,
            final_validation_fallback=_research_state_evidence_grounding_fallback,
        )
        return AgentStep(reflected, usage)


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
) -> dict[str, Any]:
    """Return one prior conclusion without evidence literals or provenance."""

    model_view = signal_result_model_view(value)
    return {
        key: model_view[key]
        for key in (
            "signal_id",
            "version",
            "state",
            "interpretation",
            "status",
        )
        if key in model_view
    }


class LLMSignalRetrievalAgent:
    """One-step selector over unexecuted compact cards in one frozen Registry."""

    def __init__(self, caller: JSONRoleCaller) -> None:
        self.caller = caller
        self.request_token_budget: int | None = None

    def set_request_token_budget(self, value: int) -> None:
        self.request_token_budget = int(value)

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
            }
            profile = dict(signal_registry.learned_profiles.get(spec.ref, {}))
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
                ref: _signal_routing_result_view(value)
                for ref, value in (prior_signal_results or {}).items()
            },
            "learned_profile_default": "no committed observations",
            "selection_caps": {"signals": 4, "llm_signals": 2},
        }
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

                def bind(
                    self,
                    paths: str | tuple[str, ...],
                    *,
                    item_id: str | None = None,
                    path_policy: str = "all",
                    repair_context: Mapping[str, Any] | None = None,
                ) -> None:
                    self.paths = (paths,) if isinstance(paths, str) else paths
                    self.item_id = item_id
                    self.path_policy = path_policy
                    self.repair_context = dict(repair_context or {})

                def append(self, message: str) -> None:
                    super().append(message)
                    self.issues.append(
                        ValidationIssue(
                            code="routing_selection_invalid",
                            message=message,
                            paths=self.paths,
                            item_id=self.item_id,
                            item_id_field=(
                                "signal_ref" if self.item_id is not None else None
                            ),
                            path_policy=self.path_policy,
                            allowed_repairs=("replace", "remove", "quarantine"),
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
                        )
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
                                    "invent a different need"
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
            direct_target_paths: dict[int, list[str]] = {}
            for item in diagnostic_items:
                if (
                    item["reason_code"] == "answer_need"
                    and item["target_shape_valid"]
                    and len(item["target_need_indices"]) == 1
                ):
                    direct_target_paths.setdefault(
                        item["target_need_indices"][0], []
                    ).append(f"selections[{item['index']}]")
            for target_index, paths in direct_target_paths.items():
                if len(paths) > 1:
                    validation_errors.bind(tuple(paths), path_policy="any")
                    validation_errors.append(
                        "one routing round permits at most one direct answer for "
                        f"information_needs[{target_index}], conflicting_paths={paths}. "
                        "Keep the smallest direct answer and classify other useful "
                        "Signals as contextual"
                    )
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
                        f"{list(answer_need_phrases)}. Change reason_code to an "
                        "accurate contextual code such as combine_evidence, or "
                        "remove the selection. research_context and selector-authored "
                        "prose cannot turn context into an answered need"
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
                "Choose the smallest unique batch from the supplied unexecuted "
                "Signal cards that answers the information needs. Previously "
                "executed Signals are omitted and must not be reconstructed. If "
                "research_context is present, use it only to test Signal "
                "applicability and complementarity; it is accepted controller state, "
                "not a new source, and contains no literal evidence. "
                "previous_context_tags contains your accepted classifications from "
                "earlier routing rounds in this case; preserve them when applying "
                "version-owned exclusions and do not omit one to bypass a card. If "
                "none of the supplied cards adds useful evidence, return "
                "{\"selections\": []}. Empty is invalid when an information need "
                "repeats the complete normalized name of an available signal_ref "
                "with at least three words or contains a supplied "
                "routing_need_phrases "
                "value; choose a non-empty answering batch in that case. A card's "
                "routing_excluded_context_tags are version-owned hard "
                "applicability exclusions: do not select that Signal when your own "
                "context_tags contain one of them. "
                "A card's routing_required_research_phrases are also hard: select "
                "that Signal only when at least one exact phrase already appears "
                "in information_needs or research_context; your new reason or "
                "applicability prose cannot create the measured object by analogy. "
                "A card's routing_answer_need_phrases are a stricter direct-answer "
                "boundary: reason_code=answer_need requires one exact phrase in "
                "the one information need named by target_need_indices. If the "
                "Signal is useful only as context, "
                "use combine_evidence or another accurate reason code instead. "
                "Use reason_code=answer_need only when the card description directly "
                "covers at least one explicit facet of an information need. Name "
                "only that facet in selection_reason and do not promise coverage of "
                "other facets. Classify answer_scope=full only when the Signal can "
                "answer every facet of the target; otherwise use partial and write "
                "residual_need as the exact natural-language question containing "
                "only unresolved facets. The residual must genuinely remove the "
                "answered facet, not cosmetically restate the old need, and must not "
                "copy a different information_needs item. Use at most "
                "one answer_need selection per target in one round; classify other "
                "useful Signals as contextual. "
                "For a non-empty answer, return "
                "selections whose items "
                "contain exactly: signal_ref; reason_code (answer_need, "
                "confirm_hypothesis, test_contradiction, assess_applicability, "
                "or combine_evidence); a <=240 character selection_reason; a "
                "<=240 character applicability_hypothesis; expected_role "
                "(primary, confirmation, contradiction, or coverage); and a "
                "target_need_indices array containing at most one integer; "
                "answer_scope (full, partial, or null); and residual_need (a <=300 "
                "character string only for partial, otherwise null); and a required "
                "context_tags array containing zero to four values from the frozen "
                "vocabulary below. "
                "answer_need requires exactly "
                "one valid index into information_needs; every other reason may use "
                "zero or one valid association index and requires null answer scope "
                "and residual, which does not mean the need was answered. Choose "
                "context_tags only from: general, "
                "comparable_financials, sparse_evidence, filing_rich, news_rich, "
                "transcript_available, market_data_only, pre_revenue, "
                "early_commercialization, scaling, mature_operations, "
                "project_driven, recurring_revenue, customer_concentrated, "
                "capital_intensive, cyclical, regulated, biotechnology, "
                "healthcare, software, semiconductors, hardware, industrial, "
                "energy, materials, consumer, financials, real_estate, "
                "communications, small_cap, mid_cap, large_cap, high_volatility, "
                "or catalyst_window."
                + _UNTRUSTED_DATA_INSTRUCTION
            ),
            payload=selection_payload,
            parser=parse,
            allow_outcomes=False,
            max_output_tokens=2_000,
            max_request_tokens=self.request_token_budget,
            stable_correction_prefix=True,
            enforce_scoped_correction=True,
            final_validation_fallback=_indexed_row_quarantine_fallback(
                "selections"
            ),
        )
        return AgentStep(selected, usage)


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

    def predict(self, final_context: Mapping[str, Any]) -> AgentStep[BlindPrediction]:
        prediction, usage = _complete_parsed_role(
            self.caller,
            stage="blind_predictor_predict",
            system_prompt=(
                "Using only the anonymous supplied context, predict whether the "
                "target security's adjusted share price reaches at least 2x over "
                "the next six calendar months. The prediction-time baseline is the "
                "mean adjusted close over the last five complete trading days, and "
                "the future numerator is the maximum mean adjusted close over any "
                "five complete consecutive trading days inside that horizon. This "
                "runtime-computed point-in-time mean is supplied as "
                "final_context.prediction_baseline. When naming the current or "
                "baseline price or computing target upside, use that supplied mean; "
                "do not relabel an older cited price observation as current. This "
                "also means market data is not absent when prediction_baseline has "
                "status=available; distinguish missing forward projections or other "
                "specific gaps from the supplied price baseline. This "
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
                + _UNTRUSTED_DATA_INSTRUCTION
                + _BLIND_PREDICTION_OUTPUT
            ),
            payload={"final_context": dict(final_context)},
            parser=lambda value: _blind_prediction_with_baseline(
                value, final_context
            ),
            allow_outcomes=False,
            anonymous_aliases=self.anonymous_aliases,
            max_output_tokens=2_000,
            max_request_tokens=self.request_token_budget,
            enforce_scoped_correction=True,
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
            compact_context = _compact_posthoc_context(original_context)
            reflection, usage = _complete_parsed_role(
                self.caller,
                stage="blind_predictor_posthoc_reflect",
                system_prompt=(
                    "The saved prediction is immutable. Given its original anonymous "
                    "compact context and newly revealed truth, reflect on the prediction. "
                    "framework_prediction_correct is deterministic and immutable; "
                    "copy it into prediction_outcome.correct and do not rejudge it. "
                    "Use candidate_judgment_feedback to distinguish binary errors, "
                    "conservative but binary-correct calls, and evidence-coverage "
                    "gaps; that feedback covers Stage 1 only, while framework "
                    "correctness also checks magnitude for a true surge. Do not "
                    "rewrite the saved four-way judgment or infer that "
                    "one realized outcome proves an ex-ante probability category. "
                    "When framework_prediction_correct is true, decision_drivers must "
                    "name at least one specific supplied evidence or counter-evidence "
                    "reason that made the saved judgment work. When it is false, "
                    "at least one of why_prediction_failed, misleading_signals, "
                    "ignored_evidence, missing_information, or plan_issues must name "
                    "a specific failure attribution; an all-empty incorrect "
                    "reflection is invalid. When compact_context.prediction_baseline "
                    "has status=available, do not claim market data is absent or was "
                    "not provided; distinguish missing forward projections or other "
                    "specific gaps from the supplied price baseline."
                    + _UNTRUSTED_DATA_INSTRUCTION
                    + _PREDICTION_REFLECTION_OUTPUT
                ),
                payload={
                    "compact_context": compact_context,
                    "original_prediction": original_prediction.to_dict(),
                    "revealed_ground_truth": ground_truth.to_dict(),
                    "framework_prediction_correct": framework_correct,
                    "candidate_judgment_feedback": judgment_feedback,
                },
                parser=lambda value: _prediction_reflection_from_role(
                    value,
                    framework_correct=framework_correct,
                    compact_context=compact_context,
                ),
                allow_outcomes=True,
                # Validated enums may equal short ticker aliases such as LOW.
                anonymous_aliases=(),
                sanitize_output_aliases=self.anonymous_aliases,
                max_output_tokens=2_000,
                max_request_tokens=self.request_token_budget,
            )
            if reflection.correct != framework_correct:
                reflection = PredictionSelfReflection(
                    correct=framework_correct,
                    decision_drivers=reflection.decision_drivers,
                    why_prediction_failed=reflection.why_prediction_failed,
                    misleading_signals=reflection.misleading_signals,
                    ignored_evidence=reflection.ignored_evidence,
                    missing_information=reflection.missing_information,
                    plan_issues=reflection.plan_issues,
                )
            return AgentStep(reflection, usage)
        except CandidateExecutionRejected as exc:
            correct = original_prediction.is_surge == ground_truth.is_surge and (
                not ground_truth.is_surge
                or original_prediction.magnitude is ground_truth.magnitude
            )
            return AgentStep(
                PredictionSelfReflection(
                    correct=correct,
                    plan_issues=(
                        "posthoc_reflection_validation_failed: " + str(exc),
                    ),
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
        meta_payload = list(
            PlanMetaMemory(maxlen=max(1, len(meta_info)), entries=meta_info).model_view()
        ) if meta_info else []
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
            "parents": [item.to_dict() for item in parents],
            "meta_info": meta_payload,
            "available_source_types": list(self.available_source_types),
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
            "Apply the fixed H_P prior. Return only evolvable Plan content: "
            "B, H_init, H_reflect, and H_analyse. B is an analyst-style source "
            "retrieval plan, not a fixed company profile or computed Signal. "
            "Meta-info is a committed retrospective FIFO. Within each entry, "
            "original_case_reflections are preserved evidence, "
            "vertical_plan_reflection adds cross-case and parent-child insight, "
            "and the top-level fields add horizontal cross-Plan insight. Use all "
            "layers without treating a later layer as a replacement for an earlier "
            "one. Outcome-aware reflection may guide the new Plan, but never change "
            "labels, metrics, or prediction semantics. Copying a selected parent's "
            "four evolvable fields verbatim is invalid. Apply the supplied "
            "proposal_context.proposal_constraints.required_change_focus through "
            "an actual content "
            "change while retaining the full four-field Plan contract."
            " Every B request is executed under the target company_id. Do not ask "
            "for general competitor, peer, or rival actions as though B searches "
            "other issuers; competitive requests must explicitly ask for the target "
            "issuer's own disclosures or target-company-scoped news mentioning "
            "competition."
            " Every B.source_types item must exactly equal a supplied "
            "available_source_types value. H_analyse may organize and weight evidence "
            "only; it must not compute a probability, classify the final Signal, "
            "change the horizon/label/four-way judgment, or generate a prediction."
            + _UNTRUSTED_DATA_INSTRUCTION
            + _INFORMATION_PLAN_OUTPUT
            + " Read fixed prior, parents, meta-info, source types, constraints, "
            "and slot metadata from proposal_context. validation_feedback is null "
            "on the initial attempt. When it is an object, correct every field "
            "named by validation_feedback.validation_error using the supplied "
            "invalid_output; preserve every unmentioned request and H_* field "
            "byte-for-byte; returning the same rejected field is not a correction."
        )
        plan_id = f"plan_r{round_id:04d}_c{candidate_index:02d}"
        parent_ids = tuple(item.plan_id for item in parents)
        parent_content_hashes = {
            _canonical_hash(item.canonical_dict()) for item in parents
        }
        failed_value: Mapping[str, Any] | None = None
        failure: ValidationError | None = None
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
            value, _usage = _complete_json_with_invalid_value(
                self.caller,
                stage=stage,
                system_prompt=system_prompt,
                payload=request_payload,
                allow_outcomes=True,
                max_output_tokens=4_000,
                temperature=self.temperature,
            )
            if self.anonymous_aliases:
                value = _mask_identity_values(value, self.anonymous_aliases)
                _scan_payload(
                    value,
                    allow_outcomes=True,
                    anonymous_aliases=self.anonymous_aliases,
                )
            try:
                if attempt and failed_value and failure is not None:
                    obligations = _validation_obligations(failure, failed_value)
                    must_change_paths = [
                        path
                        for obligation in obligations["obligations"]
                        for path in obligation["must_change_paths"]
                        if path.startswith(
                            ("B.", "B[", "H_init", "H_reflect", "H_analyse")
                        )
                    ]
                    if must_change_paths:
                        drift_paths = _scoped_correction_drift_paths(
                            failed_value,
                            value,
                            must_change_paths,
                            preserve_descendant_list_shape=True,
                        )
                        if drift_paths:
                            raise ValidationError(
                                "information_plan_propose correction changed "
                                "unrelated valid content outside "
                                f"must_change_paths={must_change_paths}, "
                                f"unrelated_changed_paths={drift_paths}. Preserve "
                                "every unrelated B request and H_* field "
                                "byte-for-byte"
                            )
                _validate_raw_information_plan_request_fields(value)
                normalized = _normalize_information_plan_output(
                    value,
                    plan_id=plan_id,
                    parent_ids=parent_ids,
                )
                plan = _parse_role_output(
                    stage, normalized, InformationPlan.from_dict
                )
                _validate_proposed_market_backbone(plan)
                _validate_proposed_request_scope(plan)
                unsupported = sorted(
                    {
                        source_type
                        for request in plan.basic_info_policy.requests
                        for source_type in request.source_types
                        if source_type not in self.available_source_types
                    }
                )
                if unsupported:
                    raise ValidationError(
                        "information_plan_propose used unsupported source types: "
                        + ", ".join(unsupported)
                    )
                _validate_fixed_plan_semantics(plan)
                _validate_proposed_plan_skills(plan)
                if _canonical_hash(plan.canonical_dict()) in parent_content_hashes:
                    raise ValidationError(
                        "candidate Plan exactly duplicates a selected parent; apply "
                        "proposal_constraints.required_change_focus and change at "
                        "least one of B, H_init, H_reflect, or H_analyse"
                    )
                _validate_proposal_change_focus(
                    plan,
                    parents,
                    focus_index=(proposal_attempt - 1) % len(change_focuses),
                )
                return plan
            except ValidationError as exc:
                failed_value = value
                failure = exc
        raise CandidateProposalRejected(
            f"information_plan_propose rejected after one correction: {failure}"
        )


def _plan_critic_trajectory(
    item: Any,
    *,
    case_index: int,
) -> dict[str, Any]:
    """Return the outcome-aware critic view without repeated source context."""

    data = dict(item.to_dict())
    compact: dict[str, Any] = {"case_index": case_index}
    for key in (
        "stop_reason",
        "termination_trigger",
        "prediction",
        "ground_truth",
        "candidate_judgment_feedback",
        "self_reflection",
    ):
        if key in data:
            compact[key] = data[key]

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
            model_result = signal_result_model_view(result)
            compact_result = {
                key: model_result[key]
                for key in (
                    "signal_id",
                    "version",
                    "state",
                    "interpretation",
                    "status",
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
        compact_rounds.append(
            {
                "information_needs": list(round_value.get("information_needs", ())),
                "selected_signals": list(round_value.get("selected_signals", ())),
                "selections": [
                    dict(item)
                    for item in round_value.get("selections", ())
                    if isinstance(item, Mapping)
                ],
                "signal_results": signal_results,
            }
        )
    compact["signal_rounds"] = compact_rounds
    return compact


def _round_reflection_record(record: PlanRecord) -> dict[str, Any]:
    """Compact one record without trajectories, identities, or per-case labels."""

    evaluation = record.evaluation
    fitness = record.fitness
    return {
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
            if self.anonymous_aliases:
                payload = _mask_identity_values(payload, self.anonymous_aliases)
                _scan_payload(
                    payload,
                    allow_outcomes=True,
                    anonymous_aliases=self.anonymous_aliases,
                )
            reflection, _usage = _complete_parsed_role(
                self.caller,
                stage="plan_critic",
                system_prompt=(
                    "Ground the reflection only in the supplied batch. Use the saved "
                    "predictions, revealed truths, deterministic candidate-judgment "
                    "feedback, post-hoc reflections, and compact Signal results to "
                    "identify successful and failed Plan patterns. Return only the "
                    "vertical cross-case and parent-child layer: the runtime preserves "
                    "every original post-hoc case reflection separately, so do not "
                    "rewrite it or present this output as its replacement. Treat four-way "
                    "feedback as diagnostic reflection evidence only; Combined "
                    "Binary F1 remains the sole fitness and parent-selection score. "
                    "Use parent_comparisons to identify structural regressions or "
                    "improvements. A metric_delta is valid only when "
                    "same_evaluation_snapshot is true; otherwise compare Plan "
                    "structure without claiming a causal metric effect. These "
                    "comparisons are reflection evidence only."
                    + _UNTRUSTED_DATA_INSTRUCTION
                    + _PLAN_REFLECTION_OUTPUT
                ),
                payload=payload,
                parser=lambda value: PlanReflection.from_dict(
                    _reject_fixed_semantics_redefinition(value)
                ),
                allow_outcomes=True,
                anonymous_aliases=self.anonymous_aliases,
                sanitize_output_aliases=self.anonymous_aliases,
                max_output_tokens=4_000,
            )
            return reflection
        except CandidateExecutionRejected as exc:
            return PlanReflection(
                failed_patterns=("plan_critic_validation_failed",),
                repeated_failure_modes=(str(exc),),
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
            return RoundMetaEntry(
                round_id=round_id,
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
            if self.anonymous_aliases:
                payload = _mask_identity_values(payload, self.anonymous_aliases)
                _scan_payload(
                    payload,
                    allow_outcomes=True,
                    anonymous_aliases=self.anonymous_aliases,
                )
            reflection, _usage = _complete_parsed_role(
                self.caller,
                stage="round_reflect",
                system_prompt=(
                    "Apply fixed H_R only to these new records; evidence_refs must cite "
                    "supplied plan ids. Return only horizontal insight across the newly "
                    "sampled child Plans. The runtime separately preserves original case "
                    "reflections and exact vertical Plan reflections; do not rewrite or "
                    "replace those layers. Use parent comparisons to identify structural "
                    "regressions or improvements. A metric_delta is valid only when "
                    "same_evaluation_snapshot is true; otherwise compare Plan "
                    "structure without claiming a causal metric effect. Parent "
                    "comparisons are reflection evidence only; Combined Binary F1 "
                    "remains the sole fitness and parent-selection score."
                    + _UNTRUSTED_DATA_INSTRUCTION
                    + _ROUND_META_OUTPUT
                ),
                payload=payload,
                parser=lambda value: RoundMetaEntry.from_dict(
                    _reject_fixed_semantics_redefinition(value)
                ),
                allow_outcomes=True,
                anonymous_aliases=self.anonymous_aliases,
                sanitize_output_aliases=self.anonymous_aliases,
                max_output_tokens=2_000,
            )
            return reflection
        except CandidateExecutionRejected as exc:
            return RoundMetaEntry(
                round_id=round_id,
                failed_patterns=("round_reflection_validation_failed: " + str(exc),),
                evidence_refs=tuple(record.plan_id for record in records),
            )
