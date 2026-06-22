"""Two-category validation: FORMAT (retryable) vs SUPPORT (escalate, never retry).

``validate_format`` enforces the *shape*: it parses the raw tool input into an
ExtractionRecord and, on failure, returns the exact violated constraints as
strings the retry loop can feed straight back to the model. (A forced tool makes
most format failures rare, but a stub or a malformed call can still produce one,
and the loop must handle it precisely.)

``check_support`` enforces *grounding*: every detected_pattern must quote a
literal that actually appears in the source text. A failure here is a
fabrication, not a shape error -- so it is handled by escalation, not by the
retry loop. Retrying "your value isn't in the source" pressures the model to
invent a more convincing one; the only safe response is to stop and route it.
"""

from pydantic import ValidationError

from contract_extraction.schemas import ExtractionRecord


def validate_format(raw: dict) -> tuple[ExtractionRecord | None, list[str]]:
    """Parse `raw` into an ExtractionRecord, or return the exact format errors."""
    try:
        return ExtractionRecord(**raw), []
    except ValidationError as exc:
        errors = []
        for err in exc.errors():
            location = ".".join(str(part) for part in err["loc"]) or "<root>"
            errors.append(f"{location}: {err['msg']}")
        return None, errors


def check_support(record: ExtractionRecord, source_text: str) -> list[str]:
    """Return support errors: cited literals absent from source, plus an uncited
    non-null governing_law.

    Two grounding failures, both escalated (never retried):

    1. A cited literal that is not a substring of the source -- a miscited value.
    2. A non-null ``governing_law`` with no citation at all. ``governing_law`` is
       the fabrication-trap field, so a value with no supporting pattern is the
       realistic adversary (guess the jurisdiction, omit the quote). Requiring a
       citation here closes the gap that the cited-literal check alone leaves open.
       Classified fields (category, indemnification) are exempt -- they are not
       read verbatim, so they carry no literal to check.
    """
    errors = []
    for pattern in record.detected_patterns:
        if pattern.literal not in source_text:
            errors.append(
                f"{pattern.field}: cited literal {pattern.literal!r} not found in source text"
            )

    cited_fields = {pattern.field for pattern in record.detected_patterns}
    if record.governing_law is not None and "governing_law" not in cited_fields:
        errors.append(
            "governing_law: non-null value carries no detected_pattern citing the source"
        )

    return errors
