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
    "compute_statistic {rule, fact_refs[2]}; read_span {fact_ref}; "
    "compare_groups {concepts}; propose_candidate {candidate}; "
    "record_deferred {}; record_no_pattern {coverage}. "
    "candidate has measurement{observable,value_kind,normalization} where "
    "value_kind is exactly one of boolean, ordinal, numeric, categorical "
    "(express any ratio as numeric), "
    "falsifiers[{condition,expected_observation}], and evidence_refs that may "
    "cite only refs from known_fact_refs, known_event_refs, or "
    "known_relation_refs; every cited ref must already be in the ledger, and "
    "at least one fetch_evidence must precede any proposal. For the "
    "hypothesis seed, the proposal must also carry need_dispositions covering "
    "every backlog need exactly once (new_measurement, deferred_measurement, "
    "update_existing, repair_dependency, not_testable, fast_plan_action). "
    "Labels arrive only through the runtime-owned label_map; never author, "
    "rewrite, or expand labels yourself. Budget wisely: fetch broadly once or "
    "twice, then compute or compare, and reserve budget for your terminal "
    "action; a seed with no budget left can only record_deferred. "
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
