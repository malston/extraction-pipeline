"""Validation has two categories, handled oppositely downstream.

FORMAT failures (missing required key, bad enum, out-of-range value) are
shape/constraint violations -- retryable, and the retry must carry the exact
violated constraint. SUPPORT failures (a detected_pattern literal that does not
appear in the source) are fabrication signals -- never retried, because retrying
"your value isn't in the source" only pressures the model to invent a better
disguise. Keeping the two categories separate is the whole point of this module.
"""

from contract_extraction.validator import check_support, validate_format


def _raw(**overrides) -> dict:
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


def test_valid_raw_parses_with_no_format_errors():
    record, errors = validate_format(_raw())
    assert errors == []
    assert record is not None
    assert record.governing_law == "Delaware"


def test_missing_required_field_is_a_format_error_naming_the_field():
    raw = _raw()
    del raw["governing_law"]
    record, errors = validate_format(raw)
    assert record is None
    assert any("governing_law" in e for e in errors)


def test_bad_enum_is_a_format_error_naming_the_constraint():
    record, errors = validate_format(_raw(indemnification="probably_fine"))
    assert record is None
    assert any("indemnification" in e for e in errors)


def test_out_of_range_value_is_a_format_error():
    record, errors = validate_format(_raw(liability_cap_usd=-5))
    assert record is None
    assert any("liability_cap_usd" in e for e in errors)


def test_supported_pattern_passes_the_source_check():
    record, _ = validate_format(_raw())
    source = "Section 20: This agreement is governed by Delaware law."
    assert check_support(record, source) == []


def test_unsupported_pattern_is_a_support_error_not_a_format_error():
    # The record is perfectly well-formed; it just cites a literal the source
    # never contained. That is fabrication, caught here, escalated -- not retried.
    record, format_errors = validate_format(_raw())
    assert format_errors == []
    source = "Section 20: The parties agree to arbitration in good faith."
    support_errors = check_support(record, source)
    assert len(support_errors) == 1
    assert "governing_law" in support_errors[0]
    assert "governed by Delaware" in support_errors[0]


def test_uncited_non_null_governing_law_is_a_support_error():
    # The realistic adversary: guess a jurisdiction and omit the citation. With no
    # pattern to miscite, the literal check finds nothing -- so the trap field gets
    # its own grounding requirement.
    record, format_errors = validate_format(
        _raw(governing_law="Delaware", detected_patterns=[])
    )
    assert format_errors == []
    support_errors = check_support(record, "no jurisdiction stated here")
    assert len(support_errors) == 1
    assert "governing_law" in support_errors[0]
    assert "no detected_pattern" in support_errors[0]


def test_null_governing_law_needs_no_citation():
    # Truthful absence must not trip the grounding requirement.
    record, _ = validate_format(_raw(governing_law=None, detected_patterns=[]))
    assert check_support(record, "no jurisdiction stated here") == []
