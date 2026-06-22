"""The `extract` tool definition and the tool_choice that forces it.

What forcing the tool DOES guarantee (syntax):
  - the response is the `extract` shape, as valid JSON;
  - every field has the declared type;
  - every enum value is in range;
  - every `required` key is present.

What it does NOT guarantee (semantics):
  - that any value is *correct*. A schema-valid record can still name the wrong
    governing law or the wrong cap. Structure stops malformed JSON; it does not
    stop a confident wrong value. That gap is why the rest of the pipeline exists
    -- the detected_pattern check, the format-retry loop, and the independent
    reviewer all attack semantics, which the schema cannot.

A `required` field with *no* nullable / NOT_SPECIFIED option is what *causes*
fabrication: the model must emit something to satisfy the schema, so on a silent
document it invents a value. Here ``governing_law`` is required-to-be-present but
its type admits ``null`` -- the truthful escape hatch the trap document depends on.

The schema is kept in lockstep with ``ExtractionRecord`` by deriving the enum
members from the same Literal types (tested in test_tool.py).
"""

from typing import get_args

from contract_extraction.schemas import Category, Indemnification

EXTRACT_TOOL = {
    "name": "extract",
    "description": (
        "Extract one structured record from a single vendor contract. Use only "
        "values that appear in the document text. When the document is silent on "
        "a nullable field, return null; when an enum has no matching member, use "
        "NOT_SPECIFIED. Never guess to fill a field."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            # Required + non-null.
            "document_id": {"type": "string"},
            "vendor_name": {"type": "string"},
            # Optional: declared, but absent from `required`, so it may be omitted.
            "vendor_contact_email": {"type": ["string", "null"]},
            # Nullable + required-present: null is the truthful "silent" value.
            "governing_law": {"type": ["string", "null"]},
            "delivery_date": {"type": ["string", "null"]},
            "net_payment_days": {"type": ["integer", "null"]},
            "early_pay_discount": {
                "type": ["object", "null"],
                "properties": {
                    "percent": {"type": "number"},
                    "within_days": {"type": "integer"},
                },
                "required": ["percent", "within_days"],
            },
            "liability_cap_usd": {"type": ["number", "null"]},
            # Enums, including NOT_SPECIFIED and the other+detail pair.
            "indemnification": {"type": "string", "enum": list(get_args(Indemnification))},
            "category": {"type": "string", "enum": list(get_args(Category))},
            "category_detail": {"type": ["string", "null"]},
            # Checkable provenance: each entry's literal must appear in the source.
            "detected_patterns": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "field": {"type": "string"},
                        "literal": {"type": "string"},
                    },
                    "required": ["field", "literal"],
                },
            },
        },
        "required": [
            "document_id",
            "vendor_name",
            "governing_law",
            "delivery_date",
            "net_payment_days",
            "early_pay_discount",
            "liability_cap_usd",
            "indemnification",
            "category",
            "category_detail",
            "detected_patterns",
        ],
    },
}

# Named tool_choice -- forces the model to return `extract` on every call, never
# free-form text and never a different tool. This is what makes the output shape
# guaranteed; `auto` would let the model decline to call it.
TOOL_CHOICE = {"type": "tool", "name": "extract"}
