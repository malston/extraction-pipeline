"""Bounded retry over FORMAT failures only -- carrying the exact constraint.

What makes a retry work is the error text: the model is told the *specific*
violated constraint ("indemnification: input should be 'capped', 'uncapped',
'none' or 'NOT_SPECIFIED'"), not a bare "try again." A vague nudge gives the
model nothing to correct.

What this loop must never do is retry missing source data. There is no retry path
for it here, by construction: a silent field is null, null is format-valid, so it
returns on the first attempt. Pushing "you didn't provide governing_law" back at
the model is what manufactures a fabricated jurisdiction -- the trap. Absence is
handled by the nullable schema, not by this loop; fabrication (a detected_pattern
that doesn't match the source) is handled by escalation, also not here.
"""

from contract_extraction.extractor import Document, ExtractorClient
from contract_extraction.schemas import ExtractionRecord
from contract_extraction.validator import validate_format


class FormatRetryExhaustedError(RuntimeError):
    """Raised when the cap is reached and the record still fails format checks."""


def format_retry_message(errors: list[str]) -> str:
    """Build the correction message that carries the exact violated constraints."""
    joined = "\n".join(f"- {error}" for error in errors)
    return (
        "Your previous extraction failed validation on these exact constraints:\n"
        f"{joined}\n"
        "Return the extract tool again, correcting only these fields. Do not change "
        "any other field, and do not invent values to satisfy a constraint -- use "
        "null or NOT_SPECIFIED where the document is silent."
    )


def extract_with_retry(
    client: ExtractorClient, document: Document, *, max_attempts: int = 3
) -> ExtractionRecord:
    """Call the extractor, retrying FORMAT failures with the exact constraint."""
    prior_error: str | None = None
    last_errors: list[str] = []
    for _ in range(max_attempts):
        raw = client.extract(document, prior_error=prior_error)
        record, errors = validate_format(raw)
        if record is not None and record.document_id != document.document_id:
            # The model must echo back the id of the document it was given. A
            # mismatch would misattribute this record's downstream review and make
            # the PipelineResult internally inconsistent -- a retryable FORMAT error.
            errors = [
                f"document_id: must be {document.document_id!r} (the id of the "
                f"document being extracted), got {record.document_id!r}"
            ]
            record = None
        if record is not None:
            return record
        last_errors = errors
        prior_error = format_retry_message(errors)
    raise FormatRetryExhaustedError(
        f"format validation failed after {max_attempts} attempts: {'; '.join(last_errors)}"
    )
