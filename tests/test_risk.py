"""RISK is categorical membership, never self-reported confidence.

A record is flagged only when it meets a *named criterion* computed from the
extracted fields -- not when a model says it feels risky. The threshold
comparisons are deterministic Python: the model supplies the fields and the
semantic call (what the cap is, whether indemnification is capped); code does
``cap > 1_000_000``. Severity is assigned by anchored rules, so each level is a
definition rather than a vibe.
"""

from decimal import Decimal

from contract_extraction.risk import ALLOWED_JURISDICTIONS, assess_risk
from contract_extraction.schemas import ExtractionRecord
from tests.test_schemas import _valid_kwargs


def _record(**overrides) -> ExtractionRecord:
    return ExtractionRecord(**_valid_kwargs(**overrides))


def test_clean_record_produces_no_finding():
    finding = assess_risk(_record(governing_law="Delaware", indemnification="capped"))
    assert finding is None


def test_uncapped_indemnification_is_critical():
    finding = assess_risk(_record(indemnification="uncapped"))
    assert finding is not None
    assert finding.severity == "CRITICAL"
    assert "uncapped_indemnification" in finding.criteria


def test_liability_cap_over_one_million_is_warning():
    finding = assess_risk(_record(liability_cap_usd=Decimal("5000000")))
    assert finding is not None
    assert finding.severity == "WARNING"
    assert "liability_cap_over_1m" in finding.criteria


def test_cap_at_exactly_one_million_does_not_flag():
    # The criterion is strictly greater-than; the boundary is deterministic code,
    # not the model eyeballing whether 1,000,000 > 1,000,000.
    assert assess_risk(_record(liability_cap_usd=Decimal("1000000"))) is None


def test_governing_law_outside_allowed_set_is_info():
    finding = assess_risk(_record(governing_law="Cayman Islands"))
    assert finding is not None
    assert finding.severity == "INFO"
    assert "governing_law_outside_allowed" in finding.criteria
    assert "Cayman Islands" not in ALLOWED_JURISDICTIONS


def test_null_governing_law_never_flags():
    # Truthful absence must not become a false positive: a silent governing_law
    # is null, and null is not "outside the allowed set."
    assert assess_risk(_record(governing_law=None)) is None


def test_most_severe_criterion_wins_when_several_match():
    finding = assess_risk(
        _record(
            indemnification="uncapped",
            liability_cap_usd=Decimal("9000000"),
            governing_law="Bermuda",
        )
    )
    assert finding.severity == "CRITICAL"
    assert set(finding.criteria) == {
        "uncapped_indemnification",
        "liability_cap_over_1m",
        "governing_law_outside_allowed",
    }
