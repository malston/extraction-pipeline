"""The records carried end-to-end -- and the four field kinds the exercise turns on.

The forced `extract` tool (tool.py) guarantees *syntax*: valid JSON, right types,
enums in range, required keys present. It guarantees nothing about *semantics* --
a schema-valid record can still hold a wrong value. These models are where the
four kinds are made distinct, because each kind exists to give the model a
truthful option so it never has to fabricate to satisfy `required`:

  - Required + non-null: ``document_id``, ``vendor_name`` -- always present.
  - Optional (omittable): ``vendor_contact_email`` -- the key may be absent.
  - Nullable (present, may be null): ``governing_law`` et al. -- the model must
    address the field, and ``null`` is the truthful "the document is silent" value.
  - Enum, incl. ``NOT_SPECIFIED`` and the ``other``+detail pair: ``indemnification``,
    ``category`` -- a named "the document doesn't say" member and a long-tail escape.

``governing_law`` is the fabrication-trap field: ``required``-to-be-*present* AND
nullable. Optional would let the model dodge by omitting it; required-non-null
would *force* a guess. Required-present + nullable is what makes truthful absence
both mandatory to address and representable.
"""

from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, Field, model_validator

Indemnification = Literal["capped", "uncapped", "none", "NOT_SPECIFIED"]
Category = Literal["services", "goods", "license", "nda", "other"]


class EarlyPayDiscount(BaseModel):
    """A "2% if paid within 10 days" early-payment discount.

    Structurally distinct from the net payment term so the two never collapse
    into one number -- the confusable case the few-shot block teaches.
    """

    percent: Decimal = Field(gt=0, le=100)
    within_days: int = Field(gt=0)


class DetectedPattern(BaseModel):
    """A claim that ``field`` was read from the literal substring ``literal``.

    The pipeline's support check (``validator.check_support``) verifies ``literal``
    actually appears in the source text -- a miscited fabrication a bare value
    would hide. Both ``field`` and ``literal`` must be non-empty: an empty citation
    token would otherwise pass the support check by trivially matching every source.
    """

    field: str = Field(min_length=1)
    literal: str = Field(min_length=1)


class ExtractionRecord(BaseModel):
    """One structured record per document (the forced ``extract`` tool's output)."""

    # Required + non-null: must always be present.
    document_id: str
    vendor_name: str

    # Optional: the key may be omitted entirely.
    vendor_contact_email: str | None = None

    # Nullable + required-present: the model must address these; ``null`` is the
    # truthful value when the source is silent. No default => the key must appear.
    governing_law: str | None
    delivery_date: str | None
    net_payment_days: int | None
    early_pay_discount: EarlyPayDiscount | None
    liability_cap_usd: Decimal | None

    # Enums: ``NOT_SPECIFIED`` is the "document doesn't say" member; ``other`` is
    # the long-tail escape, paired with the nullable ``category_detail``.
    indemnification: Indemnification
    category: Category
    category_detail: str | None

    # Required-present: the tool schema marks this required, so the validator
    # enforces the same -- a missing key is a FORMAT error (retryable), never a
    # silent disabling of the support check. An empty list is valid (a document
    # whose every value is classified rather than quoted cites nothing).
    detected_patterns: list[DetectedPattern]

    @model_validator(mode="after")
    def _check_cap_and_detail(self) -> "ExtractionRecord":
        if self.liability_cap_usd is not None and self.liability_cap_usd < 0:
            raise ValueError("liability_cap_usd must not be negative")
        if self.category == "other" and self.category_detail is None:
            raise ValueError("category_detail is required when category is 'other'")
        if self.category != "other" and self.category_detail is not None:
            raise ValueError("category_detail is only allowed when category is 'other'")
        return self
