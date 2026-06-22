"""The reviewer is a second, independent instance over the record + source.

It is handed only the artifact (the extracted record) and the source document --
never the extractor's reasoning or message history. That is the point: a model
asked to "review your own answer" in the same context rationalizes its prior
reasoning instead of catching it. A fresh instance evaluates the artifact
adversarially, with nothing to defend.
"""

from contract_extraction.reviewer import ReviewVerdict, ScriptedReviewer
from contract_extraction.validator import validate_format
from tests.test_retry import _good


def _record(**overrides):
    record, errors = validate_format(_good(**overrides))
    assert errors == []
    return record


def test_reviewer_returns_the_canned_verdict_for_the_document():
    verdict = ReviewVerdict(agrees=True, unsupported_fields=[], notes="matches source")
    reviewer = ScriptedReviewer({"doc-01": verdict})
    out = reviewer.review(_record(), "governed by Delaware")
    assert out.agrees is True
    assert out.unsupported_fields == []


def test_reviewer_only_sees_the_record_and_source():
    # Independence is structural: review() takes the artifact and the source, and
    # nothing else. The recorded call captures exactly those two inputs.
    reviewer = ScriptedReviewer(
        {"doc-01": ReviewVerdict(agrees=True, unsupported_fields=[], notes="")}
    )
    source = "Section 20: This agreement is governed by Delaware law."
    reviewer.review(_record(), source)
    assert reviewer.calls == [("doc-01", source)]


def test_reviewer_can_flag_an_unsupported_value():
    verdict = ReviewVerdict(
        agrees=False, unsupported_fields=["governing_law"], notes="not in source"
    )
    reviewer = ScriptedReviewer({"doc-01": verdict})
    out = reviewer.review(_record(governing_law="Bermuda"), "no jurisdiction stated")
    assert out.agrees is False
    assert out.unsupported_fields == ["governing_law"]
