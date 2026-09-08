"""Stable facade for the bounded evolution runtime."""

import re

from stock_opportunity_agent.research.evolution_control import *  # noqa: F403
from stock_opportunity_agent.research.evolution_control import (
    _build_evidence_resolver,
    _select_historical_plan_seed_candidates,
)
from stock_opportunity_agent.research.evolution_dataset import *  # noqa: F403
from stock_opportunity_agent.research.evolution_dataset import (
    _expansion_candidate,
    _propose_expanded_issuer_splits,
)
from stock_opportunity_agent.research.evolution_output_validation import (
    _compact_posthoc_context,
    _complete_parsed_role,
    _project_scoped_correction,
    _reject_fixed_semantics_redefinition,
    _research_state_evidence_grounding_fallback,
    _validate_proposed_plan_skills,
    _validation_obligations,
)
from stock_opportunity_agent.research.evolution_research_validation import (
    MAX_REFLECT_SIGNAL_EVIDENCE_CHARS,
    _signal_batch_model_view,
    _targeted_answer_need_transition_errors,
)
from stock_opportunity_agent.research.evolution_settings import *  # noqa: F403
from stock_opportunity_agent.research.evolution_settings import (
    _model_available_source_types,
)
from stock_opportunity_agent.research.evolution_signal_roles import *  # noqa: F403
from stock_opportunity_agent.research.evolution_signal_roles import (
    _H1_GROUP_REDEFINITION_PATTERN,
    _H1_POSITIVE_CASE_PATTERN,
    _SIGNAL_MINING_DECISIONS_OUTPUT,
    _SIGNAL_MINING_SIGNATURES_OUTPUT,
    _SIGNAL_UPDATE_OUTPUT,
    _SignalProjectionLineage,
    _map_projected_signal_evidence,
)
from stock_opportunity_agent.research.evolution_plan_roles import *  # noqa: F403
from stock_opportunity_agent.research.evolution_transport import *  # noqa: F403
from stock_opportunity_agent.research.evolution_transport import (
    _canonical_hash,
    _extract_decision_token_scores,
    _parse_json_object_envelope,
    _provider_usage_record,
    _scan_payload,
)
