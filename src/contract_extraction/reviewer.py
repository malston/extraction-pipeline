"""The independent reviewer pass -- a fresh instance over record + source.

The reviewer shares no memory with the extractor: its entire input is the
finished record and the source document. "Now review your own answer" in the same
context rationalizes the prior reasoning rather than catching it, because the
model is defending a conclusion it already committed to. A second instance,
handed only the artifact, has nothing to defend and can disagree.

``ReviewerClient`` is the seam; ``ScriptedReviewer`` replays canned verdicts
offline; ``ClaudeReviewer`` (in live.py) runs a real, separate call.
"""

from typing import Protocol

from pydantic import BaseModel

from contract_extraction.schemas import ExtractionRecord


class ReviewVerdict(BaseModel):
    """The reviewer's judgment of one record against its source."""

    agrees: bool
    unsupported_fields: list[str]
    notes: str


class ReviewerClient(Protocol):
    def review(self, record: ExtractionRecord, source_text: str) -> ReviewVerdict: ...


class ScriptedReviewer:
    """Deterministic ReviewerClient: one canned verdict per document id."""

    def __init__(self, verdicts: dict[str, ReviewVerdict]):
        self._verdicts = verdicts
        self.calls: list[tuple[str, str]] = []

    def review(self, record: ExtractionRecord, source_text: str) -> ReviewVerdict:
        self.calls.append((record.document_id, source_text))
        return self._verdicts[record.document_id]
