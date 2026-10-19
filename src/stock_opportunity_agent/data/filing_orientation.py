"""Exact SEC form qualification and bounded operating-orientation ordering."""
from __future__ import annotations

OPERATING_REQUEST_ID = "orientation.v1.operating_report"
PERIODIC_FORMS = ("10-K", "10-Q", "20-F", "40-F")
ANNUAL_FORMS = frozenset({"10-K", "20-F", "40-F"})
INTERIM_FORMS = frozenset({"10-Q"})
EXACT_FORMS = frozenset((*PERIODIC_FORMS, "8-K", "6-K"))
GENERIC_FILING_SOURCES = frozenset({"FILING", "SEC_FILING", "FILING_BODY"})


def filing_source_matches_form(source_type, form):
    """Match a generic filing alias or an exact typed source to its proved form."""
    if not isinstance(source_type, str) or not isinstance(form, str) or not form.strip():
        return False
    typed = source_type.strip().upper()
    return typed in GENERIC_FILING_SOURCES or (typed in EXACT_FORMS and typed == form.strip().upper())


def exact_document_form(document):
    """Return an exact declared form; titles and conflicting metadata prove none."""
    typed = document.source_type.strip().upper()
    if typed not in EXACT_FORMS and typed not in GENERIC_FILING_SOURCES:
        return None
    declared = document.metadata.get("form")
    if declared is not None:
        if not isinstance(declared, str):
            return None
        declared = declared.strip().upper()
        if not filing_source_matches_form(document.source_type, declared):
            return None
        return declared if declared in EXACT_FORMS else None
    return typed if typed in EXACT_FORMS else None


def operating_order(values, form_of, available_of):
    """Prefer available annual background and latest interim without requiring both."""
    values = list(values)
    recent = sorted(values, key=available_of, reverse=True)
    annual = next((item for item in recent if form_of(item) in ANNUAL_FORMS), None)
    interim = next((item for item in recent if form_of(item) in INTERIM_FORMS), None)
    first = [item for item in (annual, interim) if item is not None]
    return first + [item for item in values if not any(item is selected for selected in first)]
