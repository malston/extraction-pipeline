"""The validation-retry loop: format yes, missing data never.

A format failure is retried with the *exact* violated constraint fed back, capped
at a few attempts, then escalated. Missing source data is never retried: it is
represented as a null field, which is format-valid, so it returns on the first
attempt -- there is nothing to retry, and retrying would only pressure the model
to invent a value.
"""

import pytest

from contract_extraction.extractor import Document, ScriptedExtractor
from contract_extraction.retry import FormatRetryExhaustedError, extract_with_retry

DOC = Document(document_id="doc-01", source_text="This agreement is governed by Delaware law.")


def _good(**overrides) -> dict:
    base = dict(
        document_id="doc-01",
        vendor_name="ACME Corp",
        governing_law="Delaware",
        delivery_date=None,
        net_payment_days=None,
        early_pay_discount=None,
        liability_cap_usd=None,
        indemnification="capped",
        category="services",
        category_detail=None,
        detected_patterns=[{"field": "governing_law", "literal": "governed by Delaware"}],
    )
    base.update(overrides)
    return base


def test_format_valid_first_attempt_returns_immediately():
    client = ScriptedExtractor({"doc-01": [_good()]})
    record = extract_with_retry(client, DOC)
    assert record.vendor_name == "ACME Corp"
    assert len(client.calls) == 1
    assert client.calls[0].prior_error is None


def test_format_failure_is_retried_with_the_exact_constraint():
    client = ScriptedExtractor(
        {"doc-01": [_good(indemnification="probably_fine"), _good()]}
    )
    record = extract_with_retry(client, DOC)
    assert record.indemnification == "capped"
    assert len(client.calls) == 2
    # The second call carried the exact violated constraint, not "try again".
    assert "indemnification" in client.calls[1].prior_error


def test_retries_are_capped_then_escalate():
    client = ScriptedExtractor(
        {"doc-01": [_good(indemnification="nope")] * 5}
    )
    with pytest.raises(FormatRetryExhaustedError) as exc:
        extract_with_retry(client, DOC, max_attempts=3)
    assert len(client.calls) == 3
    assert "indemnification" in str(exc.value)


def test_silent_field_is_not_a_retry_case():
    # A document silent on governing law yields governing_law=null, which is
    # format-valid -- it returns on the first attempt. Absence is never retried.
    silent = Document(document_id="doc-01", source_text="No governing law stated.")
    client = ScriptedExtractor(
        {"doc-01": [_good(governing_law=None, detected_patterns=[])]}
    )
    record = extract_with_retry(client, silent)
    assert record.governing_law is None
    assert len(client.calls) == 1


def test_mismatched_document_id_is_retried_with_the_exact_constraint():
    # A well-formed record that echoes the wrong document_id is a FORMAT failure:
    # retried, carrying the expected id, then corrected.
    client = ScriptedExtractor(
        {"doc-01": [_good(document_id="doc-99"), _good(document_id="doc-01")]}
    )
    record = extract_with_retry(client, DOC)
    assert record.document_id == "doc-01"
    assert len(client.calls) == 2
    assert "doc-01" in client.calls[1].prior_error
    assert "doc-99" in client.calls[1].prior_error
