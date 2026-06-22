"""Routing is driven by agreement between independent instances, not confidence.

The trustworthy signal is whether two instances that never shared context reach
the same answer -- not a single model's self-reported "high confidence," which a
fluent hallucination carries just as easily as a correct answer.

  agree, nothing unsupported          -> AUTO_ACCEPT
  disagree                            -> HUMAN_REVIEW
  any unsupported value (either pass) -> ESCALATE
"""

from contract_extraction.reviewer import ReviewVerdict
from contract_extraction.routing import route


def test_agreement_auto_accepts():
    review = ReviewVerdict(agrees=True, unsupported_fields=[], notes="")
    assert route(review, support_errors=[]) == "AUTO_ACCEPT"


def test_disagreement_routes_to_human():
    review = ReviewVerdict(agrees=False, unsupported_fields=[], notes="reads differently")
    assert route(review, support_errors=[]) == "HUMAN_REVIEW"


def test_reviewer_flagged_unsupported_value_escalates():
    review = ReviewVerdict(agrees=False, unsupported_fields=["governing_law"], notes="")
    assert route(review, support_errors=[]) == "ESCALATE"


def test_pipeline_support_error_escalates_even_if_reviewer_agreed():
    # The detected_pattern check caught a fabrication the reviewer missed. The
    # programmatic signal wins -- escalate, do not auto-accept.
    review = ReviewVerdict(agrees=True, unsupported_fields=[], notes="looks fine")
    assert route(review, support_errors=["governing_law: cited literal not found"]) == "ESCALATE"
