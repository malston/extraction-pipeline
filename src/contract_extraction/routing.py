"""Confidence-based routing -- where "confidence" means inter-instance agreement.

The legitimate trust signal is agreement between the extractor and an independent
reviewer, not a single model's self-reported confidence word. So routing reads
two objective inputs: the reviewer's verdict, and the pipeline's own
detected_pattern support check. An unsupported value from *either* escalates --
the programmatic check is not overruled by a reviewer that happened to agree.
"""

from typing import Literal

from contract_extraction.reviewer import ReviewVerdict

RouteDecision = Literal["AUTO_ACCEPT", "HUMAN_REVIEW", "ESCALATE"]


def route(review: ReviewVerdict, support_errors: list[str]) -> RouteDecision:
    """Decide where a record goes from the agreement signal, not a confidence word."""
    if support_errors or review.unsupported_fields:
        return "ESCALATE"
    if review.agrees:
        return "AUTO_ACCEPT"
    return "HUMAN_REVIEW"
