"""The extractor seam: one isolated call that returns a raw `extract` record.

``ExtractorClient`` is the seam. ``ScriptedExtractor`` replays canned raw tool
inputs per document so the pipeline can be exercised offline -- including
scripting a malformed-then-corrected sequence to drive the retry loop.
``ClaudeExtractor`` (in live.py) makes the real forced-tool call.

Each call optionally carries ``prior_error``: the exact format constraint from a
failed attempt, which a real client would append to the request as a correction.
"""

from dataclasses import dataclass
from typing import Protocol

from pydantic import BaseModel


class Document(BaseModel):
    """One source document: its id and full text. The source text is what the
    detected_pattern support check is run against."""

    document_id: str
    source_text: str


class ExtractorClient(Protocol):
    def extract(self, document: Document, *, prior_error: str | None = None) -> dict: ...


@dataclass
class _Call:
    document_id: str
    prior_error: str | None


class ScriptedExtractor:
    """Deterministic ExtractorClient: replays canned raw records per document.

    Each document maps to a list of raw tool inputs, returned in order across
    attempts -- so a [malformed, corrected] list exercises one retry. Records
    every call (with the prior_error it was given) so the loop can be asserted.
    """

    def __init__(self, records: dict[str, list[dict]]):
        self._records = {doc_id: list(attempts) for doc_id, attempts in records.items()}
        self._index: dict[str, int] = {doc_id: 0 for doc_id in records}
        self.calls: list[_Call] = []

    def extract(self, document: Document, *, prior_error: str | None = None) -> dict:
        self.calls.append(_Call(document.document_id, prior_error))
        attempts = self._records[document.document_id]
        index = self._index[document.document_id]
        if index >= len(attempts):
            raise AssertionError(
                f"ScriptedExtractor exhausted for {document.document_id}: "
                "the loop asked for more attempts than were scripted."
            )
        self._index[document.document_id] = index + 1
        return attempts[index]
