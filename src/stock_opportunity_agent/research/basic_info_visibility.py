"""Compact presentation visibility, distinct from source/evidence qualification."""
from __future__ import annotations

from copy import deepcopy
from typing import Any, Mapping


_COUNT_FIELDS = ('available_projection_count', 'visible_projection_count', 'omitted_projection_count')


def basic_info_visibility(row: Mapping[str, Any]) -> dict[str, Any]:
    """Preserve two known omission layers without inferring legacy completeness."""

    coverage = row.get('coverage', {})
    source = row.get('source_context_truncated')
    if 'source_context_truncated' not in row and isinstance(coverage, Mapping):
        source = coverage.get('context_truncated')
    projection = row.get('projection_context_truncated')
    source = source if type(source) is bool else None
    projection = projection if type(projection) is bool else None
    markers = row.get('omitted_context_markers', ())
    markers = [item for item in markers if isinstance(item, str)][:16] if isinstance(markers, (list, tuple)) else []
    status = row.get('projection_status')
    omitted = row.get('omitted_projection_count')
    known_omission = (row.get('effective_context_truncated') is True
                      or status in ('partial_context_budget', 'omitted_context_budget')
                      or (type(omitted) is int and omitted > 0))
    effective = (True if source is True or projection is True or markers or known_omission
                 else False if source is False and projection is False else None)
    if status in ('complete', 'partial_context_budget', 'visibility_unknown'):
        if effective is True:
            status = 'partial_context_budget'
        elif effective is None:
            status = 'visibility_unknown'
    result = {name: deepcopy(row[name]) for name in _COUNT_FIELDS if name in row}
    if status is not None:
        result['projection_status'] = status
    result.update(source_context_truncated=source, projection_context_truncated=projection,
                  effective_context_truncated=effective, omitted_context_markers=markers)
    return result


def basic_info_source_index(
    basic: Mapping[str, Any], *, upstream: Mapping[str, Any] | None = None,
) -> list[dict[str, Any]]:
    """Project visibility, recovering known upstream omissions from saved originals."""

    saved = basic.get('source_index')
    if isinstance(saved, list):
        rows = [deepcopy(dict(row)) for row in saved if isinstance(row, Mapping)]
    else:
        rows = []
        for row in basic.get('requests', ()):
            if not isinstance(row, Mapping):
                continue
            request = row.get('request', {})
            request = request if isinstance(request, Mapping) else {}
            rows.append({'request_id': request.get('request_id'),
                         'source_types': list(request.get('source_types', ())),
                         'status': row.get('status'),
                         'projection_ids': [item['projection_id'] for item in row.get('projections', ())
                                            if isinstance(item, Mapping) and isinstance(item.get('projection_id'), str)],
                         **basic_info_visibility(row)})
    upstream_rows = {}
    if isinstance(upstream, Mapping):
        for row in upstream.get('requests', ()):
            if isinstance(row, Mapping) and isinstance(row.get('request'), Mapping):
                request_id = row['request'].get('request_id')
                if isinstance(request_id, str):
                    upstream_rows[request_id] = basic_info_visibility(row)
    result = []
    for row in rows:
        known = upstream_rows.get(row.get('request_id'))
        if known is not None:
            old_source = row.get('source_context_truncated')
            source = known['source_context_truncated']
            if old_source is True or source is True:
                row['source_context_truncated'] = True
            elif type(source) is bool:
                row['source_context_truncated'] = source
            markers = basic_info_visibility(row)['omitted_context_markers']
            row['omitted_context_markers'] = list(dict.fromkeys(
                [*known['omitted_context_markers'][:8], *markers[:8]]))
        result.append({**row, **basic_info_visibility(row)})
    return result


def pack_critic_visibility(
    trajectories: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], dict[str, dict[str, Any]]]:
    """Losslessly share visibility descriptors inside one final critic request."""
    import json

    profiles: dict[str, dict[str, Any]] = {}
    refs: dict[str, str] = {}
    packed = deepcopy(trajectories)
    for trajectory in packed:
        rows = []
        for row in trajectory.get('basic_info_source_index', ()):
            descriptor = {key: value for key, value in row.items() if key != 'projection_ids'}
            key = json.dumps(descriptor, sort_keys=True, ensure_ascii=False, separators=(',', ':'), allow_nan=False)
            if key not in refs:
                ref = 'v' + str(len(refs))
                refs[key] = ref
                profiles[ref] = descriptor
            item = {'profile_ref': refs[key]}
            if 'projection_ids' in row:
                item['projection_ids'] = row['projection_ids']
            rows.append(item)
        trajectory['basic_info_source_index'] = rows
    return packed, profiles
