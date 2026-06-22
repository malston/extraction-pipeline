"""The `extract` tool's JSON schema and the tool_choice that forces it.

Forcing the tool (named tool_choice, not auto) guarantees syntax: every call
returns the `extract` shape with valid JSON, right types, enums in range, and
required keys present. It guarantees nothing about whether the values are right.
These tests pin the schema down and confirm it stays consistent with the pydantic
ExtractionRecord it mirrors.
"""

from typing import get_args

from contract_extraction.schemas import Category, Indemnification
from contract_extraction.tool import EXTRACT_TOOL, TOOL_CHOICE


def _props() -> dict:
    return EXTRACT_TOOL["input_schema"]["properties"]


def test_tool_choice_forces_the_extract_tool_not_auto():
    # Named tool_choice -- every turn must return this tool, never free text.
    assert TOOL_CHOICE == {"type": "tool", "name": "extract"}
    assert EXTRACT_TOOL["name"] == "extract"


def test_required_array_lists_present_required_fields_only():
    required = set(EXTRACT_TOOL["input_schema"]["required"])
    # Required + non-null AND nullable-but-required-present both appear in required.
    assert {"document_id", "vendor_name", "governing_law", "indemnification"} <= required
    assert "category" in required
    # The optional field must NOT be required -- it may be omitted entirely.
    assert "vendor_contact_email" not in required


def test_nullable_fields_admit_null_in_their_type():
    # governing_law is required-present but nullable: its JSON type includes null.
    assert _props()["governing_law"]["type"] == ["string", "null"]
    assert "null" in _props()["liability_cap_usd"]["type"]


def test_enums_carry_not_specified_and_other_and_match_pydantic():
    assert set(_props()["indemnification"]["enum"]) == set(get_args(Indemnification))
    assert set(_props()["category"]["enum"]) == set(get_args(Category))
    assert "NOT_SPECIFIED" in _props()["indemnification"]["enum"]
    assert "other" in _props()["category"]["enum"]


def test_optional_field_is_declared_but_not_required():
    # Declared so the model knows it exists; absent from required so it is omittable.
    assert "vendor_contact_email" in _props()
