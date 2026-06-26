"""Offline tests for the batch result-assembly logic in ClaudeBatchExtractor.

These exercise _process_batch_results -- the failure taxonomy, document_id
tagging, and the routing of format failures to the sync retry path -- against
fake result objects. The network boundary (create/poll) is not exercised here;
the instance is built with object.__new__ so no real client is constructed.

The fakes mirror the shapes the Anthropic SDK returns: each batch result has a
custom_id and a result whose .type discriminates succeeded/errored/expired,
a succeeded result carries a .message with content blocks, and an errored
result carries .error.error.message.
"""

from types import SimpleNamespace

from contract_extraction.batch_extractor import ClaudeBatchExtractor
from contract_extraction.extractor import Document


def _succeeded(custom_id: str, tool_input: dict) -> SimpleNamespace:
    """A succeeded result whose message contains the forced extract tool_use."""
    message = SimpleNamespace(
        content=[SimpleNamespace(type="tool_use", name="extract", input=tool_input)]
    )
    return SimpleNamespace(
        custom_id=custom_id,
        result=SimpleNamespace(type="succeeded", message=message),
    )


def _succeeded_unparseable(custom_id: str) -> SimpleNamespace:
    """A succeeded result with no extract tool_use block -- a format failure."""
    message = SimpleNamespace(content=[SimpleNamespace(type="text", text="sorry")])
    return SimpleNamespace(
        custom_id=custom_id,
        result=SimpleNamespace(type="succeeded", message=message),
    )


def _errored(custom_id: str, message: str) -> SimpleNamespace:
    error = SimpleNamespace(error=SimpleNamespace(message=message))
    return SimpleNamespace(
        custom_id=custom_id,
        result=SimpleNamespace(type="errored", error=error),
    )


def _expired(custom_id: str) -> SimpleNamespace:
    return SimpleNamespace(custom_id=custom_id, result=SimpleNamespace(type="expired"))


class _FakeBatches:
    def __init__(self, results):
        self._results = results

    def results(self, batch_id):
        return iter(self._results)


class _RecordingExtractor:
    """Stands in for ClaudeExtractor, recording which documents were retried.

    behavior maps document_id to either a record dict (returned) or an
    Exception instance (raised) so a test can drive retry success or failure.
    """

    def __init__(self, behavior: dict):
        self.behavior = behavior
        self.calls: list[str] = []

    def extract(self, document: Document, *, prior_error=None) -> dict:
        self.calls.append(document.document_id)
        outcome = self.behavior[document.document_id]
        if isinstance(outcome, Exception):
            raise outcome
        return outcome


def _extractor(results, sync_behavior: dict | None = None) -> ClaudeBatchExtractor:
    instance = object.__new__(ClaudeBatchExtractor)
    instance.client = SimpleNamespace(messages=SimpleNamespace(batches=_FakeBatches(results)))
    instance.sync_extractor = _RecordingExtractor(sync_behavior or {})
    instance.model = "test-model"
    return instance


def _docs(*ids: str) -> list[Document]:
    return [Document(document_id=i, source_text=f"text for {i}") for i in ids]


def test_succeeded_results_are_tagged_with_document_id():
    docs = _docs("doc-01")
    record = {"document_id": "doc-01", "vendor_name": "ACME"}
    extractor = _extractor([_succeeded("doc-01", record)])

    results = extractor._process_batch_results("batch_1", docs)

    assert results == [
        {"document_id": "doc-01", "status": "succeeded", "record": record, "error": None}
    ]


def test_results_are_returned_in_document_order():
    docs = _docs("doc-01", "doc-02", "doc-03")
    # Results arrive out of order, as the Batch API allows.
    extractor = _extractor(
        [
            _succeeded("doc-03", {"document_id": "doc-03"}),
            _succeeded("doc-01", {"document_id": "doc-01"}),
            _succeeded("doc-02", {"document_id": "doc-02"}),
        ]
    )

    results = extractor._process_batch_results("batch_1", docs)

    assert [r["document_id"] for r in results] == ["doc-01", "doc-02", "doc-03"]


def test_unparseable_success_is_routed_to_sync_retry():
    docs = _docs("doc-01")
    retried_record = {"document_id": "doc-01", "vendor_name": "ACME"}
    extractor = _extractor(
        [_succeeded_unparseable("doc-01")],
        sync_behavior={"doc-01": retried_record},
    )

    results = extractor._process_batch_results("batch_1", docs)

    assert extractor.sync_extractor.calls == ["doc-01"]
    assert results[0]["status"] == "succeeded"
    assert results[0]["record"] == retried_record


def test_one_unparseable_result_does_not_lose_the_rest_of_the_batch():
    docs = _docs("doc-01", "doc-02")
    extractor = _extractor(
        [
            _succeeded_unparseable("doc-01"),
            _succeeded("doc-02", {"document_id": "doc-02", "vendor_name": "Globex"}),
        ],
        sync_behavior={"doc-01": {"document_id": "doc-01", "vendor_name": "ACME"}},
    )

    results = extractor._process_batch_results("batch_1", docs)

    by_id = {r["document_id"]: r for r in results}
    assert by_id["doc-01"]["status"] == "succeeded"
    assert by_id["doc-02"]["status"] == "succeeded"
    assert by_id["doc-02"]["record"]["vendor_name"] == "Globex"


def test_batch_level_errors_are_terminal_and_not_retried():
    docs = _docs("doc-01", "doc-02")
    extractor = _extractor(
        [
            _errored("doc-01", "invalid request"),
            _expired("doc-02"),
        ]
    )

    results = extractor._process_batch_results("batch_1", docs)

    # A batch-level failure must never trigger an (expensive, likely-doomed)
    # sync retry -- only a parseable-but-unparseable success is a format failure.
    assert extractor.sync_extractor.calls == []
    by_id = {r["document_id"]: r for r in results}
    assert by_id["doc-01"]["status"] == "errored"
    assert by_id["doc-01"]["error"] == "invalid request"
    assert by_id["doc-02"]["status"] == "errored"


def test_a_failed_sync_retry_is_reported_as_errored():
    docs = _docs("doc-01")
    extractor = _extractor(
        [_succeeded_unparseable("doc-01")],
        sync_behavior={"doc-01": RuntimeError("retry failed too")},
    )

    results = extractor._process_batch_results("batch_1", docs)

    assert results[0]["status"] == "errored"
    assert "retry failed too" in results[0]["error"]


def test_missing_custom_id_is_reported_errored_not_keyerror():
    docs = _docs("doc-01", "doc-02")
    # Only doc-01 comes back; doc-02 is absent from the results stream.
    extractor = _extractor([_succeeded("doc-01", {"document_id": "doc-01"})])

    results = extractor._process_batch_results("batch_1", docs)

    by_id = {r["document_id"]: r for r in results}
    assert by_id["doc-01"]["status"] == "succeeded"
    assert by_id["doc-02"]["status"] == "errored"
    assert by_id["doc-02"]["record"] is None
