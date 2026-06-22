"""Batch-vs-synchronous decision for a run of documents.

Two facts decide it, and one is a hard blocker:

  - If something is waiting on the result, or a step is *chained* on it (the next
    step cannot start until this one returns), run synchronously -- a 24-hour
    window is unacceptable when latency matters.
  - If a step needs multi-turn (the validation-retry loop sends the model its
    error and asks for a correction), it *cannot* batch at all: the Batches API
    is single-shot, no multi-turn. This is a hard constraint, not a preference.
  - Otherwise, when volume is high enough that the ~50% cost saving over a 24-hour
    window is worth the latency, batch it.

For this exercise's 10 documents the shape falls out directly: the bulk
extraction is one forced-tool call per document with nothing waiting -> batch it;
the retry of the format failures is multi-turn -> run those synchronously after
the batch returns. "Batch the bulk, sync the retries."
"""

from typing import Literal

Mode = Literal["batch", "synchronous"]

# The point below which the 24-hour turnaround is not worth the cost saving. A
# tunable heuristic: a nightly run of ten-plus documents clears it; a handful in
# an interactive flow does not.
BATCH_MIN_VOLUME = 10


def recommend_mode(*, volume: int, blocked_on_result: bool, needs_multi_turn: bool) -> Mode:
    """Recommend 'batch' or 'synchronous' for a step over `volume` documents."""
    if blocked_on_result or needs_multi_turn:
        return "synchronous"
    if volume >= BATCH_MIN_VOLUME:
        return "batch"
    return "synchronous"
