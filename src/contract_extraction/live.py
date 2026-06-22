"""Optional live path: the real forced-tool extractor and independent reviewer.

Opt-in via `poetry install --with live` and an `ANTHROPIC_API_KEY`. The whole
test suite and the offline demo run without any of this -- ScriptedExtractor and
ScriptedReviewer cover the seam. `anthropic` is imported lazily so the offline
logic here (`tool_input_from_message`, `build_extractor_messages`) works without
it.

The extractor forces the `extract` tool (TOOL_CHOICE) so every call returns the
schema shape, and ships the few-shot block in its system prompt. The reviewer is
a separate call with no extractor context -- a genuinely independent instance.

Both calls use `claude-opus-4-8`. Note the deliberate omission of thinking: a
named `tool_choice` (`{"type":"tool","name":...}`) forces tool use, which the API
rejects when extended/adaptive thinking is enabled. The exercise requires the
forced tool, so thinking stays off on these calls; consistency comes from the
forced schema and the few-shot block rather than from reasoning depth.
"""

from contract_extraction.extractor import Document
from contract_extraction.few_shot import render_few_shot
from contract_extraction.reviewer import ReviewVerdict
from contract_extraction.schemas import ExtractionRecord
from contract_extraction.tool import EXTRACT_TOOL, TOOL_CHOICE

MODEL = "claude-opus-4-8"

EXTRACTOR_SYSTEM = (
    "You extract one structured record from a single vendor contract. Use only "
    "values that appear in the document text. When the document is silent on a "
    "nullable field, return null; when an enum has no matching member, use "
    "NOT_SPECIFIED. Never guess to satisfy a required field. For every value you "
    "read VERBATIM from the source (e.g. governing_law, vendor_name, dates, "
    "amounts), add a detected_patterns entry quoting the exact substring. Do NOT "
    "add a pattern for a classified or inferred field (category, indemnification) "
    "and never invent a literal to satisfy this -- a missing quotable value stays "
    "null.\n\n"
    "Worked examples:\n\n" + render_few_shot()
)

# The reviewer judges the finished record against the source, independently.
REVIEW_TOOL = {
    "name": "review",
    "description": "Record whether the extraction is supported by the source document.",
    "input_schema": {
        "type": "object",
        "properties": {
            "agrees": {"type": "boolean"},
            "unsupported_fields": {"type": "array", "items": {"type": "string"}},
            "notes": {"type": "string"},
        },
        "required": ["agrees", "unsupported_fields", "notes"],
    },
}
REVIEW_TOOL_CHOICE = {"type": "tool", "name": "review"}

REVIEWER_SYSTEM = (
    "You are an independent reviewer. You are given a structured record and the "
    "source document it was extracted from -- nothing else. For each non-null "
    "field, check the value is actually supported by the source text. List any "
    "field whose value is not supported in unsupported_fields, and set agrees to "
    "false if you would not have produced this record. Do not assume the "
    "extractor was right; a value that is not in the source is unsupported even "
    "if it is plausible."
)


def tool_input_from_message(message, tool_name: str) -> dict:
    """Return the input of the first tool_use block named `tool_name`."""
    for block in message.content:
        if getattr(block, "type", None) == "tool_use" and block.name == tool_name:
            return block.input
    raise ValueError(f"no {tool_name!r} tool_use block in the response")


def build_extractor_messages(document: Document, prior_error: str | None) -> list[dict]:
    """Assemble the extractor request, appending the exact correction on a retry."""
    content = (
        f"Extract the record for this document.\n\n"
        f"document_id: {document.document_id}\n\n"
        f"<document>\n{document.source_text}\n</document>"
    )
    if prior_error is not None:
        content += f"\n\n{prior_error}"
    return [{"role": "user", "content": content}]


class ClaudeExtractor:
    """ExtractorClient backed by the Messages API with the forced `extract` tool."""

    def __init__(self, *, model: str = MODEL, max_tokens: int = 2048):
        import anthropic

        self._client = anthropic.Anthropic()
        self._model = model
        self._max_tokens = max_tokens

    def extract(self, document: Document, *, prior_error: str | None = None) -> dict:
        message = self._client.messages.create(
            model=self._model,
            max_tokens=self._max_tokens,
            system=EXTRACTOR_SYSTEM,
            tools=[EXTRACT_TOOL],
            tool_choice=TOOL_CHOICE,
            messages=build_extractor_messages(document, prior_error),
        )
        return tool_input_from_message(message, "extract")


class ClaudeReviewer:
    """ReviewerClient backed by a separate Messages API call -- no shared context."""

    def __init__(self, *, model: str = MODEL, max_tokens: int = 1024):
        import anthropic

        self._client = anthropic.Anthropic()
        self._model = model
        self._max_tokens = max_tokens

    def review(self, record: ExtractionRecord, source_text: str) -> ReviewVerdict:
        content = (
            f"<record>\n{record.model_dump_json(indent=2)}\n</record>\n\n"
            f"<source>\n{source_text}\n</source>"
        )
        message = self._client.messages.create(
            model=self._model,
            max_tokens=self._max_tokens,
            system=REVIEWER_SYSTEM,
            tools=[REVIEW_TOOL],
            tool_choice=REVIEW_TOOL_CHOICE,
            messages=[{"role": "user", "content": content}],
        )
        return ReviewVerdict(**tool_input_from_message(message, "review"))
