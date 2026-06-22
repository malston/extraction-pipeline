"""The runnable offline demo: honest batch vs the fabrication distractor."""

from contract_extraction.demo import run_fabrication_distractor, run_honest_batch
from contract_extraction.sample_documents import TRAP_DOCUMENT_ID


def test_honest_batch_keeps_the_trap_null_and_auto_accepts_it():
    results = run_honest_batch()
    assert len(results) == 10
    trap = next(r for r in results if r.document_id == TRAP_DOCUMENT_ID)
    assert trap.record.governing_law is None
    assert trap.decision == "AUTO_ACCEPT"
    # No record across the batch carries an unsupported (fabricated) value.
    assert all(r.support_errors == [] for r in results)


def test_fabrication_distractor_is_escalated():
    result = run_fabrication_distractor()
    assert result.record.governing_law == "Delaware"  # the model guessed
    assert result.decision == "ESCALATE"  # and the pipeline refused it
