"""The batch-vs-synchronous decision and its hard consequence.

Synchronous when something is waiting on the result or a step is chained on it.
The Batches API (~50% cheaper, up to a 24-hour window) when volume is high and
nothing is blocked. The consequence that drives the pipeline's shape: batch is
no-multi-turn, so the validation-retry loop -- which is inherently multi-turn --
cannot run inside a batch. The common shape is batch the bulk extraction, then
synchronously retry the failures.
"""

from contract_extraction.batch import BATCH_MIN_VOLUME, recommend_mode


def test_blocked_on_result_forces_synchronous_even_at_high_volume():
    mode = recommend_mode(volume=1000, blocked_on_result=True, needs_multi_turn=False)
    assert mode == "synchronous"


def test_multi_turn_step_cannot_batch():
    # The retry loop is multi-turn; batch has no multi-turn, so it must be sync.
    mode = recommend_mode(volume=1000, blocked_on_result=False, needs_multi_turn=True)
    assert mode == "synchronous"


def test_high_volume_nothing_blocked_single_turn_batches():
    assert recommend_mode(
        volume=BATCH_MIN_VOLUME, blocked_on_result=False, needs_multi_turn=False
    ) == "batch"


def test_low_volume_stays_synchronous():
    assert recommend_mode(
        volume=BATCH_MIN_VOLUME - 1, blocked_on_result=False, needs_multi_turn=False
    ) == "synchronous"


def test_the_ten_document_decision():
    # The bulk extraction over the 10 documents: nothing is waiting, one forced
    # tool call per document -> batch. The retry of the failures is multi-turn ->
    # synchronous. This is the "batch the bulk, sync the retries" shape.
    bulk_extraction = recommend_mode(volume=10, blocked_on_result=False, needs_multi_turn=False)
    retry_of_failures = recommend_mode(volume=10, blocked_on_result=False, needs_multi_turn=True)
    assert bulk_extraction == "batch"
    assert retry_of_failures == "synchronous"
