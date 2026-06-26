"""Run the extraction pipeline using the Anthropic Messages Batch API.

The pipeline reads 10 vendor documents and extracts structured records. The bulk
extraction is a single forced-tool call per document with no immediate result
dependency -- a perfect fit for batching (~50% cheaper over a 24-hour window).

The retry loop for format failures is inherently multi-turn and cannot batch;
after the batch returns, format failures are retried synchronously.

Usage:
  batch_extractor = ClaudeBatchExtractor()
  results = batch_extractor.extract_batch(documents)

Example:
  from contract_extraction.sample_documents import DOCUMENTS
  from contract_extraction.batch_extractor import ClaudeBatchExtractor

  extractor = ClaudeBatchExtractor()
  results = extractor.extract_batch(DOCUMENTS)

  for result in results:
      if result['status'] == 'succeeded':
          print(f"{result['document_id']}: {result['record']['vendor_name']}")
      else:
          print(f"{result['document_id']}: {result['error']}")
"""

import time
from typing import Any

import anthropic
from contract_extraction.extractor import Document
from contract_extraction.live import (
    EXTRACTOR_SYSTEM,
    ClaudeExtractor,
    build_extractor_messages,
)
from contract_extraction.tool import EXTRACT_TOOL, TOOL_CHOICE


class ClaudeBatchExtractor:
    """Extraction pipeline using the Anthropic Messages Batch API.

    Submits the bulk extraction to the Batches API for ~50% cost savings, then
    retries any format failures synchronously using the standard Messages API.
    """

    def __init__(self, model: str = "claude-opus-4-8"):
        self.client = anthropic.Anthropic()
        self.model = model
        self.sync_extractor = ClaudeExtractor(model=model)

    def extract_batch(
        self,
        documents: list[Document],
        poll_interval: int = 30,
        max_poll_wait: int = 3600,
    ) -> list[dict[str, Any]]:
        """Submit documents for batch extraction and wait for results.

        Args:
            documents: List of Document objects to extract
            poll_interval: Seconds between polling for batch completion
            max_poll_wait: Maximum seconds to wait for batch completion

        Returns:
            List of extraction results, one per document. Each contains:
              - document_id: str
              - status: 'succeeded' | 'errored'
              - record: extracted record (if succeeded)
              - error: error message (if errored)
        """
        # Step 1: Build batch requests
        batch_requests = self._build_batch_requests(documents)

        # Step 2: Submit batch to API
        batch = self.client.messages.batches.create(requests=batch_requests)
        batch_id = batch.id
        print(f"Submitted batch {batch_id} with {len(documents)} documents")

        # Step 3: Poll until complete
        batch = self._wait_for_batch(batch_id, poll_interval, max_poll_wait)
        print(
            f"Batch completed: {batch.request_counts.succeeded} succeeded, "
            f"{batch.request_counts.errored} errored"
        )

        # Step 4: Collect results and route format failures to sync retry
        results = self._process_batch_results(batch_id, documents)

        return results

    def _build_batch_requests(
        self, documents: list[Document]
    ) -> list[anthropic.types.messages.batch_create_params.Request]:
        """Build batch API requests for each document.

        Each request is a single forced-tool call for extraction -- no retry
        logic, no multi-turn interaction. The Batch API guarantees syntax
        validity (tool_choice forces the shape); format failures are retried
        later via the sync path.
        """
        requests = []
        for doc in documents:
            request = anthropic.types.messages.batch_create_params.Request(
                custom_id=doc.document_id,
                params=anthropic.types.message_create_params.MessageCreateParamsNonStreaming(
                    model=self.model,
                    max_tokens=2048,
                    system=EXTRACTOR_SYSTEM,
                    tools=[EXTRACT_TOOL],
                    tool_choice=TOOL_CHOICE,
                    messages=build_extractor_messages(doc, prior_error=None),
                ),
            )
            requests.append(request)
        return requests

    def _wait_for_batch(
        self, batch_id: str, poll_interval: int, max_poll_wait: int
    ) -> anthropic.types.Message:
        """Poll the batch until it completes.

        The Batches API processes asynchronously with a 24-hour window. Most
        complete within an hour, but check the returned batch for actual timing.
        """
        elapsed = 0
        while elapsed < max_poll_wait:
            batch = self.client.messages.batches.retrieve(batch_id)
            if batch.processing_status == "ended":
                return batch
            print(
                f"Batch {batch_id}: {batch.request_counts.processing} processing, "
                f"{batch.request_counts.succeeded} succeeded so far... "
                f"(elapsed: {elapsed}s)"
            )
            time.sleep(poll_interval)
            elapsed += poll_interval

        raise TimeoutError(f"Batch {batch_id} did not complete within {max_poll_wait}s")

    def _process_batch_results(
        self, batch_id: str, documents: list[Document]
    ) -> list[dict[str, Any]]:
        """Process batch results and handle format failures via sync retry.

        Batch results arrive unordered (keyed by custom_id). Format failures
        are extracted and retried synchronously using the Messages API.
        """
        # Collect batch results keyed by document_id
        batch_results = {}
        for result in self.client.messages.batches.results(batch_id):
            doc_id = result.custom_id
            if result.result.type == "succeeded":
                # Extract the tool input from the successful response
                msg = result.result.message
                record = self._extract_tool_input(msg, doc_id)
                batch_results[doc_id] = {
                    "status": "succeeded",
                    "record": record,
                    "error": None,
                }
            elif result.result.type == "errored":
                # Batch-level error (not a format error from the model). The
                # errored result wraps an ErrorResponse, whose .error holds the
                # typed error object carrying the human-readable message.
                batch_results[doc_id] = {
                    "status": "errored",
                    "record": None,
                    "error": result.result.error.error.message,
                }
            elif result.result.type == "expired":
                batch_results[doc_id] = {
                    "status": "errored",
                    "record": None,
                    "error": "Batch request expired",
                }
            elif result.result.type == "canceled":
                batch_results[doc_id] = {
                    "status": "errored",
                    "record": None,
                    "error": "Batch request canceled",
                }

        # Route format failures to sync retry
        format_failures = [
            doc for doc in documents if batch_results.get(doc.document_id, {}).get("error")
        ]
        if format_failures:
            print(f"Retrying {len(format_failures)} format failures synchronously...")
            for doc in format_failures:
                # Re-extract via the sync Messages API path, which has retry logic
                try:
                    record = self.sync_extractor.extract(doc)
                    batch_results[doc.document_id] = {
                        "status": "succeeded",
                        "record": record,
                        "error": None,
                    }
                except Exception as e:
                    batch_results[doc.document_id] = {
                        "status": "errored",
                        "record": None,
                        "error": str(e),
                    }

        # Return results in document order (for consistency with input order)
        return [batch_results[doc.document_id] for doc in documents]

    @staticmethod
    def _extract_tool_input(message: anthropic.types.Message, doc_id: str) -> dict:
        """Extract the extraction record from a tool_use block."""
        for block in message.content:
            if block.type == "tool_use" and block.name == "extract":
                return block.input
        raise ValueError(f"No tool_use block for extract in {doc_id}")


if __name__ == "__main__":
    # Demo: extract all sample documents using the Batch API
    from contract_extraction.sample_documents import DOCUMENTS

    extractor = ClaudeBatchExtractor()
    documents = DOCUMENTS

    print(f"Extracting {len(documents)} documents using Batch API...")
    results = extractor.extract_batch(documents)

    # Report results
    succeeded = [r for r in results if r["status"] == "succeeded"]
    failed = [r for r in results if r["status"] == "errored"]

    print(f"\nResults:")
    print(f"  Succeeded: {len(succeeded)}")
    print(f"  Failed: {len(failed)}")

    for result in results:
        if result["status"] == "succeeded":
            record = result["record"]
            print(
                f"  {result['document_id']}: {record.get('vendor_name', 'N/A')} "
                f"(governing_law={record.get('governing_law')})"
            )
        else:
            print(f"  {result['document_id']}: ERROR - {result['error']}")
