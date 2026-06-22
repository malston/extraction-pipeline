"""The few-shot block that ships with the extraction prompt.

Few-shot is the first lever for output consistency -- reach for it before longer
instructions or emphasis, because the model imitates concrete examples more
reliably than it parses prose rules. Two design rules are load-bearing here:

  - Cover the boundary, not the easy case, and show the *reasoning* so the model
    learns the judgment (not just the answer). The hard case below is telling an
    early-payment discount apart from the net payment term so each lands in its
    own field.
  - Include a negative example, so "don't fabricate" is demonstrated rather than
    merely asserted: a document silent on governing law maps to ``null``.

The examples must be mutually consistent. A contradiction across examples is
worse than no examples: few-shot works by pattern induction, so two examples that
map the same situation to different outputs teach the model the mapping is
arbitrary and *increase* variance. Every output below is itself schema-valid
(tested), and none contradicts another.
"""


def _base(**overrides) -> dict:
    base = dict(
        document_id="example",
        vendor_name="Example Vendor",
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


FEW_SHOT_EXAMPLES = [
    {
        "name": "discount_vs_net_term",
        "source": (
            "Invoices are payable net 30 days. A 2% discount applies if payment is "
            "received within 10 days of the invoice date."
        ),
        "reasoning": (
            "There are two distinct terms here, not one. 'Net 30 days' is the net "
            "payment window: net_payment_days = 30. The '2% ... within 10 days' is a "
            "separate early-payment incentive: early_pay_discount = {percent: 2, "
            "within_days: 10}. They must not be merged -- collapsing them into a "
            "single term would silently drop the discount, and putting 10 into "
            "net_payment_days would misstate the due date."
        ),
        "output": _base(
            document_id="example-payment",
            net_payment_days=30,
            early_pay_discount={"percent": 2, "within_days": 10},
            detected_patterns=[
                {"field": "net_payment_days", "literal": "net 30 days"},
                {
                    "field": "early_pay_discount",
                    "literal": "2% discount applies if payment is received within 10 days",
                },
            ],
        ),
    },
    {
        "name": "silent_governing_law",
        "source": (
            "Order Form -- Vendor: Example Vendor. This Order Form incorporates the "
            "Master Services Agreement by reference. It states the service category, "
            "but says nothing about which jurisdiction's law governs."
        ),
        "reasoning": (
            "The document never states a governing law. The truthful output is "
            "governing_law = null -- not a guessed jurisdiction, and not a "
            "detected_pattern, because there is no supporting text to cite. Filling "
            "this field to satisfy the schema would be fabrication; null is exactly "
            "the escape hatch the field provides for an absent value."
        ),
        "output": _base(
            document_id="example-silent",
            vendor_name="Example Vendor",
            governing_law=None,
            detected_patterns=[{"field": "vendor_name", "literal": "Example Vendor"}],
        ),
    },
]


def render_few_shot() -> str:
    """Render the examples as the text block that ships with the prompt."""
    import json

    blocks = []
    for example in FEW_SHOT_EXAMPLES:
        blocks.append(
            f"<example name={example['name']!r}>\n"
            f"SOURCE:\n{example['source']}\n\n"
            f"REASONING:\n{example['reasoning']}\n\n"
            f"EXTRACT (tool input):\n{json.dumps(example['output'], indent=2)}\n"
            f"</example>"
        )
    return "\n\n".join(blocks)
