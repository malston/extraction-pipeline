"""Categorical RISK criteria and anchored severity -- never confidence.

A gate built on "high confidence" passes fluent hallucinations: a model's
self-reported confidence has no reliable mapping to correctness, so a confident
wrong value clears the gate exactly as a confident right one does. A numeric 1-10
scale without anchoring examples just relocates the vagueness into the number --
one run's "7" is another run's "4". So the flag is defined by *named membership*
computed from the extracted fields, and each severity level carries an anchoring
example, making the level a definition rather than a vibe.

The threshold comparisons are deterministic Python. The model supplies the
fields and the semantic call; ``cap > 1_000_000`` is not the model's job.
"""

from decimal import Decimal
from typing import Literal

from pydantic import BaseModel

from contract_extraction.schemas import ExtractionRecord

Severity = Literal["CRITICAL", "WARNING", "INFO"]

# Jurisdictions the business has pre-approved. Anything else is worth a look.
ALLOWED_JURISDICTIONS = frozenset({"Delaware", "New York", "California"})

CAP_THRESHOLD = Decimal("1000000")

# Each level is anchored to a concrete example so the boundary is a definition:
#   CRITICAL -- unbounded exposure. Anchor: indemnification "uncapped"
#               (e.g. 'Vendor's indemnification obligations are unlimited').
#   WARNING  -- bounded but large exposure. Anchor: a liability cap of $5,000,000
#               (> the $1,000,000 threshold).
#   INFO     -- a fact worth a human glance. Anchor: governing law "Cayman Islands"
#               (outside the allowed {Delaware, New York, California} set).
_SEVERITY_RANK: dict[Severity, int] = {"INFO": 0, "WARNING": 1, "CRITICAL": 2}


class Finding(BaseModel):
    """A risk flag on one record: which named criteria fired, at what severity."""

    severity: Severity
    criteria: list[str]
    summary: str


def assess_risk(record: ExtractionRecord) -> Finding | None:
    """Return a Finding iff the record meets a named criterion, else None.

    Truthful absence (a null field) never fires a criterion -- it is the absence
    of a value, not a value outside an allowed set.
    """
    hits: list[tuple[Severity, str, str]] = []

    if record.indemnification == "uncapped":
        hits.append(("CRITICAL", "uncapped_indemnification", "indemnification is uncapped"))

    if record.liability_cap_usd is not None and record.liability_cap_usd > CAP_THRESHOLD:
        hits.append(
            ("WARNING", "liability_cap_over_1m", f"liability cap ${record.liability_cap_usd}")
        )

    if record.governing_law is not None and record.governing_law not in ALLOWED_JURISDICTIONS:
        hits.append(
            (
                "INFO",
                "governing_law_outside_allowed",
                f"governing law {record.governing_law!r} outside allowed set",
            )
        )

    if not hits:
        return None

    severity = max((s for s, _, _ in hits), key=lambda s: _SEVERITY_RANK[s])
    return Finding(
        severity=severity,
        criteria=[name for _, name, _ in hits],
        summary="; ".join(detail for _, _, detail in hits),
    )
