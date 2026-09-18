"""Live role adapter between the mining controller and a JSON role caller.

Bridges the fixed controller action protocol onto any ``JSONRoleCaller``
(the same structured transport the production Slow roles use), so a shadow
cycle can drive the LabelAwareMiningController with the real DeepSeek client
while every call stays inside the ordinary attempt/cost ledger. The adapter
translates views to payloads and model output to action objects; contract
enforcement stays entirely in the controller.
"""

from __future__ import annotations

from typing import Any, Mapping

from stock_opportunity_agent.research.evolution_core import AgentUsage

MINING_CONTROLLER_STAGE = "mining_controller_step"

_MINING_CONTROLLER_PROMPT = (
    "You are the bounded decision core of a label-aware Signal-mining "
    "controller over a point-in-time Evidence Graph. The runtime owns tools, "
    "the ledger, budgets, labels, and termination; you only choose one action "
    "per step. Return exactly one JSON object with keys action and rationale "
    "plus the action's own fields. rationale is a non-empty array of short "
    "strings. Allowed actions and their required fields: "
    "inspect_manifest {}; inspect_catalog {}; "
    "fetch_evidence {case_refs, source_families, max_documents, query|null} "
    "where source_families may list several families in one call and every "
    "family must come from available_source_families in the view; sweep the "
    "evidence you need in as few fetches as possible; "
    "compute_statistic {rule, fact_refs[2]}; read_span with exactly one "
    "of {fact_ref | event_ref | document_ref} (event/document reads take "
    "bounded offset/length and charge the separate browse budget; raw "
    "narrative text is the authoritative narrative evidence); "
    "inspect_catalog {scope: signals|evidence} where scope=evidence "
    "returns the discovery-only family -> window -> document directory; "
    "compare_groups {concepts}; propose_candidate {candidate}; "
    "record_deferred {}; record_no_pattern {coverage}. "
    "candidate has measurement{observable,value_kind,normalization} where "
    "value_kind is exactly one of boolean, ordinal, numeric, categorical "
    "(express any ratio as numeric), "
    "falsifiers[{condition,expected_observation}], and evidence_refs that may "
    "cite only refs from known_fact_refs, known_event_refs, or "
    "known_relation_refs. For a narrative measurement, include "
    "measurement.predicate{modality:narrative, source_families, "
    "lookback_days, semantic_condition, threshold{field,operator,value}} "
    "whose source_families intersect your cited narrative evidence. "
    "When narrative_summary headlines or attribute_case_coverage show a "
    "positive-versus-control contrast (for example order confirmations "
    "appearing only in positive cases), a narrative predicate measurement "
    "citing those event refs is a first-class candidate and often serves "
    "several backlog needs at once. "
    "prior_modality_footprints carries earlier cycles' modality metrics and "
    "staged_candidate_outcomes — each prior candidate's real check-cohort "
    "result (tp/fn/fp/tn, availability, disposition). A semantic family "
    "whose fires never overlap the positive class (tp near zero, fn high) "
    "is a demonstrated predicate-label mismatch: propose a different "
    "narrative contrast instead of re-proposing the same semantic family. "
    "Every cited ref must already be in the ledger, at "
    "least one fetch_evidence must precede any proposal, and every known "
    "concept named in the observable or normalization (compare_groups results "
    "show the fact_ref behind each value) must be backed by at least one "
    "cited fact of that concept. The observable "
    "must be a genuinely new measurement: it may not reuse or version any "
    "signal_ref base name from signal_catalog, because changing an existing "
    "Signal belongs to the separate Update path. "
    "For the hypothesis seed, the proposal must also carry need_dispositions "
    "covering every backlog need exactly once (new_measurement, "
    "deferred_measurement, update_existing, repair_dependency, not_testable, "
    "fast_plan_action); each row is {need_refs, disposition, signal_refs, "
    "rationale} where only update_existing cites exactly one existing signal "
    "ref and every other disposition cites none. "
    "evidence_digest summarizes what your fetches have already collected "
    "(families, per-concept positive/control case coverage) and "
    "last_action_result reports what your previous action returned; use them "
    "instead of re-fetching families that are already covered, and spend "
    "remaining budget on compute_statistic, compare_groups, or your terminal "
    "action. Once heavy_remaining reaches 0, only inspect_manifest, "
    "inspect_catalog, record_no_pattern, and record_deferred remain "
    "admissible; repeating a heavy action then ends the seed as "
    "deferred_budget. Labels arrive only through the runtime-owned label_map; never "
    "author, rewrite, or expand labels yourself. Budget wisely: fetch broadly "
    "once or twice, then compute or compare, and reserve budget for your "
    "terminal action; a seed with no budget left can only record_deferred. "
    "Domain terminals are inadmissible while modality_coverage shows "
    "narrative available but unexplored: fetch or read narrative evidence, "
    "inspect the evidence catalog, or take a control-plane terminal. "
    "record_no_pattern must cite "
    "explored_families actually present in your own prior fetches. When "
    "last_invalid_action is present, fix exactly that issue. Never request "
    "facts after the prediction time, never use identities or file ordering "
    "as features, and never exceed the remaining budgets shown in the view."
)


class MiningAgentRoleModel:
    """Adapt one JSON role caller to the controller's ``next_action`` shape."""

    def __init__(
        self,
        caller: Any,
        *,
        stage: str = MINING_CONTROLLER_STAGE,
        max_output_tokens: int = 4000,
        temperature: float = 0.2,
    ) -> None:
        self.caller = caller
        self.stage = stage
        self.max_output_tokens = max_output_tokens
        self.temperature = temperature
        self.usage = AgentUsage()
        self.requests: list[str] = []

    def next_action(self, view: Mapping[str, Any]) -> dict[str, Any]:
        """Send one controller view and return the model's action object."""

        parsed, usage = self.caller.complete_json(
            stage=self.stage,
            system_prompt=_MINING_CONTROLLER_PROMPT,
            payload=dict(view),
            allow_outcomes=True,
            max_output_tokens=self.max_output_tokens,
            temperature=self.temperature,
        )
        self.usage = AgentUsage(
            llm_calls=self.usage.llm_calls + usage.llm_calls,
            tokens=self.usage.tokens + usage.tokens,
            cost=self.usage.cost + usage.cost,
        )
        trace = getattr(self.caller, "request_hash_trace", ())
        if isinstance(trace, (list, tuple)):
            self.requests.extend(str(item) for item in trace[len(self.requests) :])
        if not isinstance(parsed, Mapping):
            from stock_opportunity_agent.models import ValidationError

            raise ValidationError("mining controller action must be an object")
        return dict(parsed)
