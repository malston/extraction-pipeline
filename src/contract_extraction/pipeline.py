"""The pipeline for one document and for the batch.

Per document: extract (with the format-only retry loop) -> check support against
the source -> assess categorical risk -> independent reviewer pass -> route on
the agreement signal. The result carries every intermediate so the routing
decision is fully auditable.

In production the shape follows batch.py: the bulk extraction is a batch job, and
only the format failures are retried synchronously afterward. Offline this runs
sequentially, but the *handling* is the same -- a format failure is retried with
the exact constraint; a support failure (fabrication) is never retried, it
escalates; truthful absence is a null field that needs neither.

A document whose format the model never gets right (the retry loop exhausts its
cap) is itself an escalation case, not a crash: `run_document` turns it into an
ESCALATE result carrying the exhaustion reason, so one unrecoverable document in a
batch escalates on its own rather than discarding every other document's result.
"""

from pydantic import BaseModel

from contract_extraction.extractor import Document, ExtractorClient
from contract_extraction.retry import FormatRetryExhaustedError, extract_with_retry
from contract_extraction.reviewer import ReviewerClient, ReviewVerdict
from contract_extraction.risk import Finding, assess_risk
from contract_extraction.routing import RouteDecision, route
from contract_extraction.schemas import ExtractionRecord
from contract_extraction.validator import check_support


class PipelineResult(BaseModel):
    document_id: str
    # record and review are absent only when the format-retry loop exhausted its
    # cap -- there is no valid record to review. `error` carries that reason; for a
    # completed document it is None and `support_errors` holds any grounding issues.
    record: ExtractionRecord | None
    finding: Finding | None
    support_errors: list[str]
    review: ReviewVerdict | None
    decision: RouteDecision
    error: str | None = None


def run_document(
    document: Document,
    extractor: ExtractorClient,
    reviewer: ReviewerClient,
    *,
    max_attempts: int = 3,
) -> PipelineResult:
    try:
        record = extract_with_retry(extractor, document, max_attempts=max_attempts)
    except FormatRetryExhaustedError as exc:
        # A document we cannot coerce into valid shape after the retry cap is a
        # human-review case, not a batch-killing exception. ESCALATE it with the
        # exact reason instead of letting it abort the surrounding batch.
        return PipelineResult(
            document_id=document.document_id,
            record=None,
            finding=None,
            support_errors=[],
            review=None,
            decision="ESCALATE",
            error=str(exc),
        )
    support_errors = check_support(record, document.source_text)
    finding = assess_risk(record)
    review = reviewer.review(record, document.source_text)
    decision = route(review, support_errors)
    return PipelineResult(
        document_id=document.document_id,
        record=record,
        finding=finding,
        support_errors=support_errors,
        review=review,
        decision=decision,
    )


def run_batch(
    documents: list[Document],
    extractor: ExtractorClient,
    reviewer: ReviewerClient,
    *,
    max_attempts: int = 3,
) -> list[PipelineResult]:
    return [run_document(doc, extractor, reviewer, max_attempts=max_attempts) for doc in documents]
