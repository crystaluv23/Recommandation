"""Closed versioned bootstrap actions compiled into general Raw Info requests."""
from __future__ import annotations

from dataclasses import replace
from typing import Mapping
from stock_opportunity_agent.data.resolution import RawInfoRequest, source_types_compatible
from stock_opportunity_agent.data.filing_orientation import PERIODIC_FORMS
from stock_opportunity_agent.models import StructuredValidationError, ValidationIssue

MENU_VERSION = "basic-info-orientation-v1"
# Fixed descriptions are runtime values, not authored research instructions.
_ACTIONS = {
    "market_backbone": ("Orient recent point-in-time price and volume; preserve exact runtime measurements and their observation windows.", "market_data", 120, 2, 45, 1, None),
    "operating_report": ("Orient the business model, risks and segment economics from available annual or interim operating reports. Prefer annual background and latest interim when available; source presence does not prove every fact was visible or answered.", "filing", 730, 5, 730, 2, "business operations segments products services customers risks"),
    "management_commentary": ("Orient management commentary on operations and stated outlook from point-in-time complete meeting content; retain scope and availability gaps.", "earnings_call", 365, 3, 365, 1, None),
    "scoped_news": ("Orient recent issuer-specific developments in operations, customers, financing, regulation and products; limited retrieval is not absence.", "news", 365, 5, 180, 5, None),
    "financial_facts": ("Orient reported growth, margins, cash and capital structure from point-in-time financial facts; preserve period, unit and data gaps.", "sec_company_facts", 730, 3, 730, 2, None),
}


def make_orientation_request(action, *, lookback_days=None, max_documents=None):
    """Construct the exact canonical template with only bounded parameter choices."""
    description, source, _days, _count, default_days, default_count, _query = _ACTIONS[action]
    return RawInfoRequest(request_id="orientation.v1."+action, description=description,
        source_types=(source,), lookback_days=default_days if lookback_days is None else lookback_days,
        max_documents=default_count if max_documents is None else max_documents)


def orientation_menu(available_source_types=None):
    """Expose fixed action values, parameter bounds and the implementation recipe."""
    menu = {"version": MENU_VERSION, "actions": [{"action": action,
        "request": make_orientation_request(action).to_dict(),
        "bounds": {"lookback_days": [1, row[2]], "max_documents": [1, row[3]]},
        "internal_fixed_query": row[6], "plan_query_allowed": False}
        for action, row in _ACTIONS.items()]}
    if available_source_types is not None:
        available = tuple(available_source_types)
        menu["available_action_ids"] = [
            item["request"]["request_id"] for item in menu["actions"]
            if source_types_compatible(item["request"]["source_types"], available)
        ]
    return menu


def compile_basic_info_requests(policy):
    """Validate every action before compiling fixed source coverage and query."""
    requests = policy.requests
    issues = []
    compiled = []
    for index, request in enumerate(requests):
        path = f"B.requests[{index}]"
        action = request.request_id.removeprefix("orientation.v1.")
        if request.request_id != "orientation.v1."+action or action not in _ACTIONS:
            issues.append(ValidationIssue(code="basic_info_action_unknown", paths=(path+".request_id",),
                message="Choose an exact action request from the versioned orientation menu", allowed_repairs=("replace",)))
            continue
        template = make_orientation_request(action)
        row = _ACTIONS[action]
        checks = ((request.description == template.description, "description"),
                  (request.source_types == template.source_types, "source_types"),
                  (request.query is None, "query"),
                  (type(request.lookback_days) is int and 1 <= request.lookback_days <= row[2], "lookback_days"),
                  (type(request.max_documents) is int and 1 <= request.max_documents <= row[3], "max_documents"),
                  (not request.required_source_groups, "required_source_groups"),
                  (request.minimum_distinct_periods is None, "minimum_distinct_periods"),
                  (request.minimum_period_span_days is None, "minimum_period_span_days"),
                  (request.minimum_observations is None, "minimum_observations"))
        for valid, field in checks:
            if not valid:
                issues.append(ValidationIssue(code="basic_info_action_parameter_invalid", paths=(path+"."+field,),
                    message="Use fixed orientation template values and published integer parameter bounds; Plan query/coverage are not authorable", allowed_repairs=(("replace",) if field in {"description","source_types","lookback_days","max_documents"} else ("replace","remove"))))
        if all(valid for valid, _field in checks):
            compiled.append(replace(request, query=row[6],
                required_source_groups=(PERIODIC_FORMS,) if action == "operating_report" else ()))
    if issues:
        raise StructuredValidationError(issues)
    return tuple(compiled)


def validate_raw_orientation_policy(data):
    """Reject non-integer proposal parameters before legacy archive coercion."""
    rows = data.get("requests", ()) if isinstance(data, Mapping) else ()
    issues = []
    if not isinstance(data, Mapping) or "requests" not in data:
        issues.append(ValidationIssue(code="basic_info_action_parameter_invalid", paths=("B.requests",), message="Use the versioned orientation requests array", allowed_repairs=("add","replace")))
    if isinstance(data, Mapping):
        for field in set(data)-{"requests"}:
            issues.append(ValidationIssue(code="basic_info_action_parameter_invalid", paths=("B."+str(field),), message="Unknown orientation policy fields are not supported", allowed_repairs=("remove",)))
    if not isinstance(rows, (list, tuple)):
        raise StructuredValidationError((ValidationIssue(code="basic_info_action_parameter_invalid", paths=("B.requests",), message="Requests must be an array of fixed orientation action objects", allowed_repairs=("replace",)),))
    known = {"request_id", "description", "source_types", "lookback_days", "max_documents",
             "query", "required_source_groups", "minimum_distinct_periods",
             "minimum_period_span_days", "minimum_observations"}
    for index, row in enumerate(rows):
        if not isinstance(row, Mapping):
            issues.append(ValidationIssue(code="basic_info_action_parameter_invalid", paths=(f"B.requests[{index}]",), message="Use a fixed orientation action object", allowed_repairs=("replace",)))
            continue
        for field in set(row)-known:
            issues.append(ValidationIssue(code="basic_info_action_parameter_invalid", paths=(f"B.requests[{index}].{field}",), message="Unknown orientation request fields are not supported", allowed_repairs=("remove",)))
        for field in ("lookback_days", "max_documents"):
            if field in row and type(row[field]) is not int:
                issues.append(ValidationIssue(code="basic_info_action_parameter_invalid", paths=(f"B.requests[{index}].{field}",),
                    message="Orientation parameters must be JSON integers, not coerced strings, booleans or fractions", allowed_repairs=("replace",)))
    if issues:
        raise StructuredValidationError(issues)
