"""Ten worked vendor documents for the offline demo and the tests.

One of them -- doc-07, Wayne Enterprises -- is the fabrication trap: it never
states a governing law. The honest extraction returns governing_law=null; a
fabricating extraction (FABRICATED_TRAP_EXTRACTION) guesses "Delaware" and cites
a literal that is not in the source, which the support check catches.

Every honest extraction below is fully grounded: each detected_pattern literal is
a verbatim substring of its document's source text (asserted in the tests), and
silent fields are null with no pattern. doc-08 is scripted with a malformed first
attempt (a bad enum) to exercise the retry loop; doc-09's reviewer disagrees on a
supported value, to exercise HUMAN_REVIEW routing.
"""

from contract_extraction.extractor import Document, ScriptedExtractor
from contract_extraction.reviewer import ReviewVerdict, ScriptedReviewer

TRAP_DOCUMENT_ID = "doc-07"


def _extraction(**overrides) -> dict:
    base = dict(
        document_id="",
        vendor_name="",
        vendor_contact_email=None,
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


DOCUMENTS = [
    Document(
        document_id="doc-01",
        source_text=(
            "Vendor: ACME Corp. This Services Agreement is governed by Delaware law. "
            "Invoices payable net 30 days, with a 2% discount if paid within 10 days. "
            "Total liability shall not exceed $500,000. Vendor shall indemnify "
            "Customer subject to the liability cap."
        ),
    ),
    Document(
        document_id="doc-02",
        source_text=(
            "Vendor: Globex Industries. Governed by New York law. This agreement "
            "covers the supply of goods. Aggregate liability shall not exceed "
            "$5,000,000. Indemnification is capped at the liability limit."
        ),
    ),
    Document(
        document_id="doc-03",
        source_text=(
            "Vendor: Initech LLC. This software license is governed by California "
            "law. Vendor's indemnification obligations under this Agreement are "
            "unlimited and uncapped. Net 45 days."
        ),
    ),
    Document(
        document_id="doc-04",
        source_text=(
            "Vendor: Umbrella Services Ltd. This agreement is governed by the laws "
            "of the Cayman Islands. Liability capped at $250,000. Indemnification "
            "capped at the liability limit."
        ),
    ),
    Document(
        document_id="doc-05",
        source_text=(
            "Vendor: Soylent Corp (contact: legal@soylent.example). This Mutual NDA "
            "is governed by California law. Liability is capped at $100,000. The "
            "parties owe no indemnification under this NDA."
        ),
    ),
    Document(
        document_id="doc-06",
        source_text=(
            "Vendor: Stark Industries. This revenue-share arrangement is governed "
            "by Delaware law. Delivery date: 2026-09-01. Liability capped at "
            "$750,000. Indemnification capped at the liability limit."
        ),
    ),
    Document(
        document_id="doc-07",
        source_text=(
            "Vendor: Wayne Enterprises. This Statement of Work covers consulting "
            "services. Net 60 days. Liability shall not exceed $300,000. "
            "Indemnification is capped at the liability limit. The document does "
            "not state a governing jurisdiction."
        ),
    ),
    Document(
        document_id="doc-08",
        source_text=(
            "Vendor: Wonka Industries. Governed by New York law. This goods supply "
            "agreement. Liability capped at $400,000. Indemnification capped at the "
            "liability limit."
        ),
    ),
    Document(
        document_id="doc-09",
        source_text=(
            "Vendor: Cyberdyne Systems. Governed by Delaware law. This services "
            "agreement. Liability shall not exceed $1,200,000. Indemnification "
            "capped at the liability limit."
        ),
    ),
    Document(
        document_id="doc-10",
        source_text=(
            "Vendor: Tyrell Corp. Governed by California law. This software license "
            "agreement. Net 30 days. Liability capped at $900,000. Indemnification "
            "capped at the liability limit."
        ),
    ),
]


EXTRACTIONS: dict[str, list[dict]] = {
    "doc-01": [
        _extraction(
            document_id="doc-01",
            vendor_name="ACME Corp",
            governing_law="Delaware",
            net_payment_days=30,
            early_pay_discount={"percent": 2, "within_days": 10},
            liability_cap_usd=500000,
            indemnification="capped",
            category="services",
            detected_patterns=[
                {"field": "vendor_name", "literal": "ACME Corp"},
                {"field": "governing_law", "literal": "governed by Delaware law"},
                {"field": "net_payment_days", "literal": "net 30 days"},
                {"field": "early_pay_discount", "literal": "2% discount if paid within 10 days"},
                {"field": "liability_cap_usd", "literal": "$500,000"},
            ],
        )
    ],
    "doc-02": [
        _extraction(
            document_id="doc-02",
            vendor_name="Globex Industries",
            governing_law="New York",
            liability_cap_usd=5000000,
            indemnification="capped",
            category="goods",
            detected_patterns=[
                {"field": "vendor_name", "literal": "Globex Industries"},
                {"field": "governing_law", "literal": "Governed by New York law"},
                {"field": "liability_cap_usd", "literal": "$5,000,000"},
            ],
        )
    ],
    "doc-03": [
        _extraction(
            document_id="doc-03",
            vendor_name="Initech LLC",
            governing_law="California",
            net_payment_days=45,
            indemnification="uncapped",
            category="license",
            detected_patterns=[
                {"field": "vendor_name", "literal": "Initech LLC"},
                {"field": "governing_law", "literal": "governed by California"},
                {"field": "indemnification", "literal": "unlimited and uncapped"},
                {"field": "net_payment_days", "literal": "Net 45 days"},
            ],
        )
    ],
    "doc-04": [
        _extraction(
            document_id="doc-04",
            vendor_name="Umbrella Services Ltd",
            governing_law="Cayman Islands",
            liability_cap_usd=250000,
            indemnification="capped",
            category="services",
            detected_patterns=[
                {"field": "vendor_name", "literal": "Umbrella Services Ltd"},
                {"field": "governing_law", "literal": "Cayman Islands"},
                {"field": "liability_cap_usd", "literal": "$250,000"},
            ],
        )
    ],
    "doc-05": [
        _extraction(
            document_id="doc-05",
            vendor_name="Soylent Corp",
            vendor_contact_email="legal@soylent.example",
            governing_law="California",
            liability_cap_usd=100000,
            indemnification="none",
            category="nda",
            detected_patterns=[
                {"field": "vendor_name", "literal": "Soylent Corp"},
                {"field": "vendor_contact_email", "literal": "legal@soylent.example"},
                {"field": "governing_law", "literal": "governed by California law"},
                {"field": "liability_cap_usd", "literal": "$100,000"},
            ],
        )
    ],
    "doc-06": [
        _extraction(
            document_id="doc-06",
            vendor_name="Stark Industries",
            governing_law="Delaware",
            delivery_date="2026-09-01",
            liability_cap_usd=750000,
            indemnification="capped",
            category="other",
            category_detail="revenue-share arrangement",
            detected_patterns=[
                {"field": "vendor_name", "literal": "Stark Industries"},
                {"field": "governing_law", "literal": "governed by Delaware law"},
                {"field": "delivery_date", "literal": "2026-09-01"},
                {"field": "category_detail", "literal": "revenue-share arrangement"},
                {"field": "liability_cap_usd", "literal": "$750,000"},
            ],
        )
    ],
    "doc-07": [
        _extraction(
            document_id="doc-07",
            vendor_name="Wayne Enterprises",
            governing_law=None,  # the document is silent -- truthful null
            net_payment_days=60,
            liability_cap_usd=300000,
            indemnification="capped",
            category="services",
            detected_patterns=[
                {"field": "vendor_name", "literal": "Wayne Enterprises"},
                {"field": "net_payment_days", "literal": "Net 60 days"},
                {"field": "liability_cap_usd", "literal": "$300,000"},
            ],
        )
    ],
    "doc-08": [
        # First attempt: a bad enum value -> format failure -> retried.
        _extraction(
            document_id="doc-08",
            vendor_name="Wonka Industries",
            governing_law="New York",
            liability_cap_usd=400000,
            indemnification="limited",  # not a valid enum member
            category="goods",
            detected_patterns=[
                {"field": "vendor_name", "literal": "Wonka Industries"},
                {"field": "governing_law", "literal": "Governed by New York law"},
                {"field": "liability_cap_usd", "literal": "$400,000"},
            ],
        ),
        # Corrected attempt.
        _extraction(
            document_id="doc-08",
            vendor_name="Wonka Industries",
            governing_law="New York",
            liability_cap_usd=400000,
            indemnification="capped",
            category="goods",
            detected_patterns=[
                {"field": "vendor_name", "literal": "Wonka Industries"},
                {"field": "governing_law", "literal": "Governed by New York law"},
                {"field": "liability_cap_usd", "literal": "$400,000"},
            ],
        ),
    ],
    "doc-09": [
        _extraction(
            document_id="doc-09",
            vendor_name="Cyberdyne Systems",
            governing_law="Delaware",
            liability_cap_usd=1200000,
            indemnification="capped",
            category="services",
            detected_patterns=[
                {"field": "vendor_name", "literal": "Cyberdyne Systems"},
                {"field": "governing_law", "literal": "Governed by Delaware law"},
                {"field": "liability_cap_usd", "literal": "$1,200,000"},
            ],
        )
    ],
    "doc-10": [
        _extraction(
            document_id="doc-10",
            vendor_name="Tyrell Corp",
            governing_law="California",
            net_payment_days=30,
            liability_cap_usd=900000,
            indemnification="capped",
            category="license",
            detected_patterns=[
                {"field": "vendor_name", "literal": "Tyrell Corp"},
                {"field": "governing_law", "literal": "Governed by California law"},
                {"field": "net_payment_days", "literal": "Net 30 days"},
                {"field": "liability_cap_usd", "literal": "$900,000"},
            ],
        )
    ],
}


def _agree(note: str = "matches source") -> ReviewVerdict:
    return ReviewVerdict(agrees=True, unsupported_fields=[], notes=note)


REVIEWS: dict[str, ReviewVerdict] = {
    "doc-01": _agree(),
    "doc-02": _agree(),
    "doc-03": _agree(),
    "doc-04": _agree(),
    "doc-05": _agree(),
    "doc-06": _agree(),
    "doc-07": _agree("governing law correctly left null; nothing in source states it"),
    "doc-08": _agree(),
    # A genuine disagreement on a supported value: the reviewer reads the cap as
    # per-claim rather than aggregate. No fabrication -- just a different reading.
    "doc-09": ReviewVerdict(
        agrees=False,
        unsupported_fields=[],
        notes="cap may be per-claim, not aggregate; needs a human",
    ),
    "doc-10": _agree(),
}


# The distractor: a fabricating extraction of the trap document. It guesses
# "Delaware" and cites a literal that does NOT appear in doc-07's source.
FABRICATED_TRAP_EXTRACTION = _extraction(
    document_id="doc-07",
    vendor_name="Wayne Enterprises",
    governing_law="Delaware",  # fabricated -- the source is silent
    net_payment_days=60,
    liability_cap_usd=300000,
    indemnification="capped",
    category="services",
    detected_patterns=[
        {"field": "vendor_name", "literal": "Wayne Enterprises"},
        # This literal is not in doc-07's source -- the support check will catch it.
        {"field": "governing_law", "literal": "governed by Delaware law"},
    ],
)


def build_extractor() -> ScriptedExtractor:
    return ScriptedExtractor(EXTRACTIONS)


def build_reviewer() -> ScriptedReviewer:
    return ScriptedReviewer(REVIEWS)
