"""End-to-end through the pipeline -- the headline fabrication-trap test.

The trap document (doc-07) never states a governing law. It must come back as
null and survive every stage as null: the nullable schema lets it, the retry loop
never fires on it (null is format-valid), and the reviewer agrees the null is
correct. A fabricating extraction that guesses a jurisdiction is caught by the
detected_pattern support check and escalated -- never auto-accepted.
"""

from contract_extraction.extractor import Document, ScriptedExtractor
from contract_extraction.pipeline import run_batch, run_document
from contract_extraction.reviewer import ReviewVerdict, ScriptedReviewer
from contract_extraction.sample_documents import (
    DOCUMENTS,
    EXTRACTIONS,
    FABRICATED_TRAP_EXTRACTION,
    REVIEWS,
    TRAP_DOCUMENT_ID,
    build_extractor,
    build_reviewer,
)

_SOURCE = {doc.document_id: doc.source_text for doc in DOCUMENTS}
_TRAP_DOC = next(d for d in DOCUMENTS if d.document_id == TRAP_DOCUMENT_ID)


def test_trap_document_stays_not_specified_end_to_end():
    result = run_document(_TRAP_DOC, build_extractor(), build_reviewer())
    assert result.record.governing_law is None  # truthful absence survived
    assert result.support_errors == []
    assert result.finding is None  # null never triggers a risk criterion
    assert result.decision == "AUTO_ACCEPT"


def test_no_fabricated_field_across_all_ten_records():
    results = run_batch(DOCUMENTS, build_extractor(), build_reviewer())
    assert len(results) == 10
    for result in results:
        source = _SOURCE[result.document_id]
        # Every value the model claims to have read is grounded in the source.
        for pattern in result.record.detected_patterns:
            assert pattern.literal in source, f"{result.document_id}/{pattern.field}"
        assert result.support_errors == []
    trap = next(r for r in results if r.document_id == TRAP_DOCUMENT_ID)
    assert trap.record.governing_law is None


def test_fabricating_extractor_on_the_trap_is_caught_and_escalated():
    # Same trap document, but the extractor guesses "Delaware" and cites a literal
    # that is not in the source. The support check catches it; routing escalates.
    extractor = ScriptedExtractor({TRAP_DOCUMENT_ID: [FABRICATED_TRAP_EXTRACTION]})
    reviewer = ScriptedReviewer(
        {
            TRAP_DOCUMENT_ID: ReviewVerdict(
                agrees=False, unsupported_fields=["governing_law"], notes="not in source"
            )
        }
    )
    result = run_document(_TRAP_DOC, extractor, reviewer)
    assert result.record.governing_law == "Delaware"  # the model did fabricate
    assert result.support_errors  # but the support check caught it
    assert any("governing_law" in e for e in result.support_errors)
    assert result.decision == "ESCALATE"  # so it never auto-accepts


def test_uncited_fabrication_on_the_trap_is_caught_even_if_reviewer_agrees():
    # The realistic adversary: guess "Delaware" and omit the citation entirely, so
    # the cited-literal check has nothing to flag. The trap-field grounding rule
    # catches it, and routing escalates even though the reviewer was fooled.
    uncited = dict(
        document_id=TRAP_DOCUMENT_ID,
        vendor_name="Wayne Enterprises",
        governing_law="Delaware",  # fabricated, with no supporting pattern
        delivery_date=None,
        net_payment_days=60,
        early_pay_discount=None,
        liability_cap_usd=300000,
        indemnification="capped",
        category="services",
        category_detail=None,
        detected_patterns=[{"field": "vendor_name", "literal": "Wayne Enterprises"}],
    )
    extractor = ScriptedExtractor({TRAP_DOCUMENT_ID: [uncited]})
    reviewer = ScriptedReviewer(
        {TRAP_DOCUMENT_ID: ReviewVerdict(agrees=True, unsupported_fields=[], notes="looks fine")}
    )
    result = run_document(_TRAP_DOC, extractor, reviewer)
    assert any("governing_law" in e for e in result.support_errors)
    assert result.decision == "ESCALATE"


def test_format_failure_is_retried_inside_the_pipeline():
    extractor = build_extractor()
    doc_08 = next(d for d in DOCUMENTS if d.document_id == "doc-08")
    result = run_document(doc_08, extractor, build_reviewer())
    assert result.record.indemnification == "capped"  # corrected value
    doc_08_calls = [c for c in extractor.calls if c.document_id == "doc-08"]
    assert len(doc_08_calls) == 2  # one failure, one correction
    assert "indemnification" in doc_08_calls[1].prior_error


def test_disagreement_routes_to_human():
    doc_09 = next(d for d in DOCUMENTS if d.document_id == "doc-09")
    result = run_document(doc_09, build_extractor(), build_reviewer())
    assert result.review.agrees is False
    assert result.support_errors == []
    assert result.decision == "HUMAN_REVIEW"


def test_risk_findings_are_categorical_across_severities():
    results = {r.document_id: r for r in run_batch(DOCUMENTS, build_extractor(), build_reviewer())}
    assert results["doc-01"].finding is None
    assert results["doc-02"].finding.severity == "WARNING"  # $5M cap
    assert results["doc-03"].finding.severity == "CRITICAL"  # uncapped indemnification
    assert results["doc-04"].finding.severity == "INFO"  # Cayman Islands


# A document whose every attempt carries a bad enum -- the retry loop can never
# produce a valid record for it.
_UNFORMATTABLE = dict(
    document_id="doc-bad",
    vendor_name="Broken Co",
    governing_law=None,
    delivery_date=None,
    net_payment_days=None,
    early_pay_discount=None,
    liability_cap_usd=None,
    indemnification="totally_made_up",  # never a valid enum member
    category="services",
    category_detail=None,
    detected_patterns=[],
)


def test_exhausted_retry_escalates_instead_of_raising():
    bad_doc = Document(document_id="doc-bad", source_text="unparseable contract")
    extractor = ScriptedExtractor({"doc-bad": [_UNFORMATTABLE] * 5})
    result = run_document(bad_doc, extractor, build_reviewer(), max_attempts=3)
    assert result.decision == "ESCALATE"
    assert result.record is None
    assert result.review is None
    assert result.error is not None
    assert "indemnification" in result.error


def test_one_unformattable_document_does_not_abort_the_batch():
    # The bad document escalates on its own; the nine good documents still return
    # their results rather than being discarded by a propagating exception.
    bad_doc = Document(document_id="doc-bad", source_text="unparseable contract")
    documents = DOCUMENTS[:9] + [bad_doc]
    good_ids = {doc.document_id for doc in DOCUMENTS[:9]}
    extractions = {doc_id: EXTRACTIONS[doc_id] for doc_id in good_ids}
    extractions["doc-bad"] = [_UNFORMATTABLE] * 5
    reviews = {doc_id: REVIEWS[doc_id] for doc_id in good_ids}
    extractor = ScriptedExtractor(extractions)
    reviewer = ScriptedReviewer(reviews)

    results = run_batch(documents, extractor, reviewer)
    assert len(results) == 10
    by_id = {r.document_id: r for r in results}
    assert by_id["doc-bad"].decision == "ESCALATE"
    assert by_id["doc-bad"].record is None
    # The good documents were not discarded.
    assert by_id["doc-01"].record is not None
    assert by_id["doc-01"].decision == "AUTO_ACCEPT"
