"""The live-path logic worth testing offline: reading a forced tool_use result
and assembling the retry correction. The network wrappers (ClaudeExtractor /
ClaudeReviewer) are a thin, key-gated boundary exercised against the real API.
"""

from types import SimpleNamespace

import pytest

from contract_extraction.extractor import Document
from contract_extraction.live import build_extractor_messages, tool_input_from_message


def _message(*blocks) -> SimpleNamespace:
    return SimpleNamespace(content=list(blocks))


def test_pulls_the_forced_tool_input_by_name():
    message = _message(
        SimpleNamespace(type="text", text="here is the record"),
        SimpleNamespace(type="tool_use", name="extract", input={"document_id": "doc-01"}),
    )
    assert tool_input_from_message(message, "extract") == {"document_id": "doc-01"}


def test_raises_when_the_forced_tool_is_absent():
    message = _message(SimpleNamespace(type="text", text="no tool call"))
    with pytest.raises(ValueError, match="extract"):
        tool_input_from_message(message, "extract")


def test_first_attempt_carries_the_source_and_no_correction():
    doc = Document(document_id="doc-01", source_text="governed by Delaware law")
    messages = build_extractor_messages(doc, prior_error=None)
    user_text = messages[0]["content"]
    assert "governed by Delaware law" in user_text
    assert "correcting" not in user_text.lower()


def test_retry_attempt_appends_the_exact_correction():
    doc = Document(document_id="doc-01", source_text="governed by Delaware law")
    messages = build_extractor_messages(
        doc, prior_error="indemnification: input should be 'capped' ..."
    )
    user_text = messages[0]["content"]
    assert "indemnification: input should be" in user_text
