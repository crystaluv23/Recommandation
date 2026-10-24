"""Bounded-context distillation worker over Raw Info originals.

The distiller is the subagent form of the disclosure interface's fetch
layer: it receives one complete original document (or an exact section) in
its own bounded context and returns a structured distillation card — an
event summary, quantified facts quoted verbatim (the runtime locates each
quote in the original and owns its coordinates), a source character, and
limitations. The card and its references flow back to the calling context;
the original never does.

Deterministic validation guarantees the card is checkable: every quote must
be an exact substring of the original, and every number in the summary must
occur inside a quoted literal, so restated arithmetic cannot enter the card.
"""

from __future__ import annotations

import re
from typing import Any, Iterable, Mapping

from stock_opportunity_agent.data.raw_info import RawInfoStore
from stock_opportunity_agent.models import (
    StructuredValidationError,
    ValidationError,
    ValidationIssue,
)
from stock_opportunity_agent.research.evolution_core import AgentStep
from stock_opportunity_agent.research.evolution_output_validation import (
    _complete_parsed_role,
    _UNTRUSTED_DATA_INSTRUCTION,
)

_MAX_DISTILL_INPUT_CHARS = 200_000
_MAX_SUMMARY_CHARS = 600
_MAX_QUOTED_FACTS = 6
_MAX_QUOTE_CHARS = 400
_NUMBER_PATTERN = re.compile(r"\d[\d,]*(?:\.\d+)?")

_DISTILLER_SYSTEM_PROMPT = (
    "Distill the supplied complete original document under the given focus "
    "conditions. Return only a distillation card object: event_summary "
    "(what happened, who, when — no numbers you invented), quantified_facts "
    "(array of {quote}: every number-bearing fact copied verbatim from the "
    "document text, at most 6 quotes, each at most 400 characters), "
    "source_character (issuer_disclosure or third_party_reporting), and "
    "limitations (string array). Numbers may appear only inside verbatim "
    "quotes; the event_summary may reference a quoted number but must never "
    "restate a different or derived value. Do not infer contents that are "
    "not present."
    + _UNTRUSTED_DATA_INSTRUCTION
)


def _numeric_tokens(text: str) -> set[str]:
    return set(_NUMBER_PATTERN.findall(text))


def _validate_distillation_card(
    value: Mapping[str, Any], original_text: str
) -> dict[str, Any]:
    allowed = {"event_summary", "quantified_facts", "source_character", "limitations"}
    if not isinstance(value, Mapping) or set(value) != allowed:
        raise ValidationError(
            "distillation card must contain exactly "
            f"{sorted(allowed)}, got {sorted(set(value))}"
        )
    summary = value["event_summary"]
    if not isinstance(summary, str) or not summary.strip():
        raise ValidationError("distillation event_summary must be nonempty text")
    if len(summary) > _MAX_SUMMARY_CHARS:
        raise ValidationError(
            f"distillation event_summary exceeds {_MAX_SUMMARY_CHARS} characters"
        )
    if value["source_character"] not in {
        "issuer_disclosure",
        "third_party_reporting",
    }:
        raise ValidationError("distillation source_character is invalid")
    raw_facts = value["quantified_facts"]
    if not isinstance(raw_facts, list) or len(raw_facts) > _MAX_QUOTED_FACTS:
        raise ValidationError(
            "distillation quantified_facts must be an array of at most "
            f"{_MAX_QUOTED_FACTS} quotes"
        )
    if not isinstance(value["limitations"], list) or any(
        not isinstance(item, str) for item in value["limitations"]
    ):
        raise ValidationError("distillation limitations must be a string array")
    quotes: list[dict[str, Any]] = []
    for index, fact in enumerate(raw_facts):
        if not isinstance(fact, Mapping) or set(fact) != {"quote"}:
            raise ValidationError(
                f"distillation quantified_facts[{index}] must be an object "
                "with exactly a quote field"
            )
        quote = fact["quote"]
        if not isinstance(quote, str) or not quote.strip():
            raise ValidationError(
                f"distillation quantified_facts[{index}].quote must be nonempty"
            )
        if len(quote) > _MAX_QUOTE_CHARS:
            raise ValidationError(
                f"distillation quantified_facts[{index}].quote exceeds "
                f"{_MAX_QUOTE_CHARS} characters"
            )
        occurrences = original_text.count(quote)
        if occurrences < 1:
            raise ValidationError(
                f"distillation quantified_facts[{index}].quote is not a "
                "verbatim substring of the original document"
            )
        start = original_text.find(quote)
        quotes.append(
            {
                "quote": quote,
                "raw_start": start,
                "raw_end": start + len(quote),
                "occurrence_count": occurrences,
            }
        )
    quoted_numbers: set[str] = set()
    for row in quotes:
        quoted_numbers |= _numeric_tokens(row["quote"])
    unexplained = _numeric_tokens(summary) - quoted_numbers
    if unexplained:
        raise ValidationError(
            "distillation event_summary restates numbers absent from the "
            f"quoted facts: {sorted(unexplained)}"
        )
    return {
        "schema_version": "raw-info-distillation-card-v1",
        "event_summary": summary,
        "quantified_facts": quotes,
        "source_character": value["source_character"],
        "limitations": list(value["limitations"]),
    }


class RawInfoDistiller:
    """Distill one complete original into a verifiable card in its own context."""

    def __init__(self, caller: Any) -> None:
        self.caller = caller

    def distill(
        self,
        store: RawInfoStore,
        reference: Mapping[str, Any],
        *,
        as_of: Any,
        focus: str = "",
    ) -> AgentStep[dict[str, Any]]:
        """Return one validated distillation card with provenance references.

        Usage example (scripted caller):

            step = RawInfoDistiller(caller).distill(
                store, {"document_id": doc_id, "content_hash": h}, as_of=as_of,
            )
            step.value["quantified_facts"][0]["raw_start"]
        """

        document_id = reference.get("document_id")
        content_hash = reference.get("content_hash")
        if not isinstance(document_id, str) or not isinstance(content_hash, str):
            raise ValidationError(
                "distillation reference requires document_id and content_hash"
            )
        document = store.load(document_id, as_of=as_of)
        if document.content_hash != content_hash:
            raise ValidationError(
                "distillation reference content hash does not match the document"
            )
        raw_start = int(reference.get("raw_start", 0))
        raw_end = int(
            reference.get("raw_end", len(document.content))
        )
        if not 0 <= raw_start < raw_end <= len(document.content):
            raise ValidationError("distillation reference offsets are invalid")
        original_text = document.content[raw_start:raw_end]
        if len(original_text) > _MAX_DISTILL_INPUT_CHARS:
            raise ValidationError(
                "distillation input exceeds the bounded subagent context; "
                "fetch an exact section reference instead"
            )

        def parse(value: Mapping[str, Any]) -> dict[str, Any]:
            try:
                return _validate_distillation_card(value, original_text)
            except ValidationError as exc:
                raise StructuredValidationError(
                    (
                        ValidationIssue(
                            code="distillation_card_invalid",
                            message=str(exc),
                            paths=("distillation_card",),
                            allowed_repairs=("replace", "remove"),
                        ),
                    )
                ) from exc

        card, usage = _complete_parsed_role(
            self.caller,
            stage="raw_info_distiller",
            system_prompt=_DISTILLER_SYSTEM_PROMPT,
            payload={
                "focus": focus,
                "reference": {
                    "document_id": document_id,
                    "content_hash": content_hash,
                    "raw_start": raw_start,
                    "raw_end": raw_end,
                },
                "document_text": original_text,
            },
            parser=parse,
            allow_outcomes=False,
            max_output_tokens=8_000,
        )
        card["reference"] = {
            "document_id": document_id,
            "content_hash": content_hash,
            "raw_start": raw_start,
            "raw_end": raw_end,
        }
        return AgentStep(card, usage)


def quoted_fact_refs(card: Mapping[str, Any]) -> tuple[str, ...]:
    """Content-addressed references for every quote in one distillation card."""

    reference = card.get("reference")
    if not isinstance(reference, Mapping):
        return ()
    return tuple(
        "distill:{document_id}:{content_hash}:{raw_start}:{raw_end}".format(
            **{**reference, "raw_start": fact["raw_start"], "raw_end": fact["raw_end"]}
        )
        for fact in card.get("quantified_facts", ())
        if isinstance(fact, Mapping)
    )
