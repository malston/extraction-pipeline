"""The ExtractionRecord schema must demonstrate all four field kinds distinctly.

Required (present + non-null), optional (omittable), nullable (present, may be
null when the source is silent), and enums (including NOT_SPECIFIED and the
other+detail pair). The pydantic-level distinctions are what the JSON tool schema
in tool.py mirrors for the real API.
"""

from decimal import Decimal

import pytest
from pydantic import ValidationError

from contract_extraction.schemas import EarlyPayDiscount, ExtractionRecord


def _valid_kwargs(**overrides) -> dict:
    base = dict(
        document_id="doc-01",
        vendor_name="ACME Corp",
        governing_law=None,
        delivery_date=None,
        net_payment_days=None,
        early_pay_discount=None,
        liability_cap_usd=None,
        indemnification="NOT_SPECIFIED",
        category="services",
        category_detail=None,
        detected_patterns=[],
    )
    base.update(overrides)
    return base


def test_required_fields_must_be_present():
    kwargs = _valid_kwargs()
    del kwargs["document_id"]
    with pytest.raises(ValidationError, match="document_id"):
        ExtractionRecord(**kwargs)


def test_optional_field_may_be_omitted_entirely():
    # vendor_contact_email is omittable -- a valid record need not carry the key.
    record = ExtractionRecord(**_valid_kwargs())
    assert record.vendor_contact_email is None


def test_nullable_field_is_required_to_be_present_but_may_be_null():
    # governing_law is the fabrication-trap field: it must be PRESENT (so the
    # model cannot dodge by omitting it) and null is the truthful "silent" value.
    kwargs = _valid_kwargs()
    del kwargs["governing_law"]
    with pytest.raises(ValidationError, match="governing_law"):
        ExtractionRecord(**kwargs)

    record = ExtractionRecord(**_valid_kwargs(governing_law=None))
    assert record.governing_law is None


def test_enum_accepts_not_specified_and_rejects_out_of_range():
    record = ExtractionRecord(**_valid_kwargs(indemnification="uncapped"))
    assert record.indemnification == "uncapped"
    with pytest.raises(ValidationError, match="indemnification"):
        ExtractionRecord(**_valid_kwargs(indemnification="probably_fine"))


def test_other_category_requires_a_detail_string():
    # The other+detail pair: "other" without a detail is the long-tail value with
    # no explanation -- a constraint violation the format-retry loop can catch.
    with pytest.raises(ValidationError, match="category_detail"):
        ExtractionRecord(**_valid_kwargs(category="other", category_detail=None))

    record = ExtractionRecord(
        **_valid_kwargs(category="other", category_detail="revenue-share agreement")
    )
    assert record.category_detail == "revenue-share agreement"


def test_detail_without_other_category_is_rejected():
    # A detail string on a named category is contradictory -- the detail belongs
    # only to the "other" escape hatch.
    with pytest.raises(ValidationError, match="category_detail"):
        ExtractionRecord(**_valid_kwargs(category="services", category_detail="stray note"))


def test_negative_liability_cap_is_out_of_range():
    with pytest.raises(ValidationError, match="liability_cap_usd"):
        ExtractionRecord(**_valid_kwargs(liability_cap_usd=Decimal("-1")))


def test_early_pay_discount_is_a_structured_nested_value():
    record = ExtractionRecord(
        **_valid_kwargs(
            net_payment_days=30,
            early_pay_discount=EarlyPayDiscount(percent=Decimal("2"), within_days=10),
        )
    )
    assert record.early_pay_discount.percent == Decimal("2")
    assert record.early_pay_discount.within_days == 10
    assert record.net_payment_days == 30


def test_empty_detected_pattern_literal_is_rejected():
    # An empty literal would trivially be a substring of any source, letting an
    # uncited fabrication pass check_support. The schema forbids it outright.
    with pytest.raises(ValidationError, match="literal"):
        ExtractionRecord(
            **_valid_kwargs(
                governing_law="Delaware",
                detected_patterns=[{"field": "governing_law", "literal": ""}],
            )
        )


def test_empty_detected_pattern_field_is_rejected():
    # Same trivial-match hazard on the field side -- an empty field name is not a
    # real citation target.
    with pytest.raises(ValidationError, match="field"):
        ExtractionRecord(
            **_valid_kwargs(
                governing_law="Delaware",
                detected_patterns=[{"field": "", "literal": "Delaware"}],
            )
        )


def test_missing_detected_patterns_key_is_rejected():
    # The tool schema marks detected_patterns required; the validator enforces the
    # same, so a missing key cannot silently disable the support check.
    kwargs = _valid_kwargs()
    del kwargs["detected_patterns"]
    with pytest.raises(ValidationError, match="detected_patterns"):
        ExtractionRecord(**kwargs)
