"""Runnable offline demo: `python -m contract_extraction.demo`.

Drives the real pipeline with the deterministic seam (no API key) along two
trajectories:

  - honest:      the 10 documents extracted truthfully. The trap document
                 (doc-07), silent on governing law, comes back null and
                 auto-accepts. No record carries a fabricated value.
  - distractor:  the same trap document, but the extractor guesses "Delaware"
                 and cites a literal absent from the source. The support check
                 catches it and routing escalates -- the guess never auto-accepts.
"""

from contract_extraction.extractor import ScriptedExtractor
from contract_extraction.pipeline import PipelineResult, run_batch, run_document
from contract_extraction.reviewer import ReviewVerdict, ScriptedReviewer
from contract_extraction.sample_documents import (
    DOCUMENTS,
    FABRICATED_TRAP_EXTRACTION,
    TRAP_DOCUMENT_ID,
    build_extractor,
    build_reviewer,
)


def run_honest_batch() -> list[PipelineResult]:
    return run_batch(DOCUMENTS, build_extractor(), build_reviewer())


def run_fabrication_distractor() -> PipelineResult:
    trap_doc = next(d for d in DOCUMENTS if d.document_id == TRAP_DOCUMENT_ID)
    extractor = ScriptedExtractor({TRAP_DOCUMENT_ID: [FABRICATED_TRAP_EXTRACTION]})
    reviewer = ScriptedReviewer(
        {
            TRAP_DOCUMENT_ID: ReviewVerdict(
                agrees=False, unsupported_fields=["governing_law"], notes="not in source"
            )
        }
    )
    return run_document(trap_doc, extractor, reviewer)


def main() -> None:
    print("=== honest batch (10 documents) ===")
    for result in run_honest_batch():
        severity = result.finding.severity if result.finding else "-"
        trap = "  <- fabrication trap" if result.document_id == TRAP_DOCUMENT_ID else ""
        print(
            f"  {result.document_id}  {result.decision:<12}  "
            f"governing_law={result.record.governing_law!r:<18}  risk={severity}{trap}"
        )

    print("\n=== distractor: fabricating extractor on the trap document ===")
    result = run_fabrication_distractor()
    print(f"  extracted governing_law={result.record.governing_law!r} (guessed)")
    for error in result.support_errors:
        print(f"  SUPPORT FAILURE: {error}")
    print(f"  decision: {result.decision}")


if __name__ == "__main__":
    main()
