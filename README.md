# Domain 4 -- Contract Extraction Pipeline

A runnable, test-driven implementation of the CCA Domain 4 build exercise. A
pipeline reads 10 vendor documents, forces each through a `tool_use` JSON schema,
flags risk by **categorical criteria** (never confidence), retries **format**
failures with the exact violated constraint, and verifies every record with an
**independent reviewer** pass. One document is silent on its governing law -- and
that truthful absence must survive end to end as `null`, never a guessed
jurisdiction.

- The design doc this implements: [`../deliverables/domain4-build-exercise.md`](../deliverables/domain4-build-exercise.md)
- The exercise prompt: [`../.prompts/domain4-build-exercise.prompt.md`](../.prompts/domain4-build-exercise.prompt.md)

## Quick start

```bash
poetry install --with dev
poetry run pytest                          # NO API key needed
poetry run python -m contract_extraction.demo
```

The demo runs the pipeline along two trajectories of the same trap document:

```
=== honest batch (10 documents) ===
  doc-07  AUTO_ACCEPT   governing_law=None                risk=-  <- fabrication trap
  ...

=== distractor: fabricating extractor on the trap document ===
  extracted governing_law='Delaware' (guessed)
  SUPPORT FAILURE: governing_law: cited literal 'governed by Delaware law' not found in source text
  decision: ESCALATE
```

The only difference is whether the extractor told the truth. When the document is
silent, `null` survives; when the model guesses, the support check catches the
fabricated citation and the record is escalated, never auto-accepted.

## The linchpin

The **fabrication-trap document** (doc-07, silent on governing law) ends as
`governing_law = None` at every stage, and no field in any of the 10 records holds
a value absent from its source. Three mechanisms, in order, prevent the guess:

1. **Schema (`schemas.py`, `tool.py`).** `governing_law` is `required`-to-be-
   _present_ **and** nullable. Optional would let the model dodge by omitting it;
   required-non-null would _force_ a guess. Required-present + nullable makes
   `null` both mandatory to address and truthful to return.
2. **Retry (`retry.py`).** The format-retry loop never fires on the trap: a null
   field is format-valid, so there is nothing to retry. Retrying "you didn't
   provide governing_law" is exactly what manufactures a fabricated jurisdiction.
3. **Support check + reviewer (`validator.py`, `reviewer.py`, `routing.py`).** A
   fabricated value carries a `detected_pattern` that is not in the source; the
   support check catches it (`UNSUPPORTED`, never retried) and an independent
   reviewer flags it. Either signal routes the record to `ESCALATE`.

See `tests/test_pipeline.py` (`test_trap_document_stays_not_specified_end_to_end`,
`test_no_fabricated_field_across_all_ten_records`) and the defended distractor
(`test_fabricating_extractor_on_the_trap_is_caught_and_escalated`).

## How the deliverables map to code

| Deliverable                               | Where                                   | Correct pattern (demonstrated)                                                     | Distractor (shown failing/defended)                           |
| ----------------------------------------- | --------------------------------------- | ---------------------------------------------------------------------------------- | ------------------------------------------------------------- |
| 1. Forced tool + 4 field kinds            | `tool.py`, `schemas.py`                 | `tool_choice` forces `extract`; required / optional / nullable / enum all distinct | A `required` non-null `governing_law` -- forces a guess       |
| 2. Categorical RISK + anchored severity   | `risk.py`                               | Named criteria from extracted fields; `cap > 1_000_000` in code; anchored levels   | A "high-confidence" gate that passes fluent hallucinations    |
| 3. Few-shot: reasoning + negative         | `few_shot.py`                           | Discount-vs-net-term reasoning trace + a silent->null negative example             | Easy-case-only examples, or contradictory examples            |
| 4. Format-only retry + `detected_pattern` | `retry.py`, `validator.py`              | Retry carries the exact constraint; support failure escalates, never retries       | Retrying missing data -- pressures the model to invent        |
| 5. Independent reviewer + routing         | `reviewer.py`, `routing.py`, `batch.py` | Fresh instance; route on **agreement**; batch the bulk, sync the retries           | "Review your own answer"; route on a self-reported confidence |

## What forcing the tool does and does not buy you

Forcing `extract` (named `tool_choice`, not `auto`) guarantees **syntax**: valid
JSON, declared types, enums in range, required keys present. It guarantees nothing
about **semantics** -- a schema-valid record can still name the wrong governing
law. Structure stops malformed JSON; it does not stop a confident wrong value.
That gap is the entire reason the rest of the pipeline exists: the
`detected_pattern` support check, the retry loop, and the independent reviewer all
attack semantics, which the schema cannot. (`tool.py` states this in full.)

## Two judgments the model never makes

- **The `$1M` threshold comparison.** The model supplies the cap and the semantic
  call (is this a liability cap?); `risk.assess_risk` does `cap > 1_000_000` and
  assigns severity by anchored rule. Letting an LLM eyeball a financial threshold
  is the "define what counts, never ask how confident" violation wearing a number.
- **Whether a cited value is grounded.** `validator.check_support` checks each
  `detected_pattern` literal against the source text in code -- catching a
  _miscited_ fabrication a bare value would hide. Note the boundary: it validates
  cited provenance, so a fabrication that omits its citation entirely is not
  caught here -- that case rests on the independent reviewer, which is why the
  reviewer is a genuine second check, not a rubber stamp.

## The batch decision for these 10 documents

Nothing is waiting on the result and each extraction is a single forced-tool call,
so the **bulk extraction batches** (~50% cheaper, up to a 24-hour window). The
**retry loop is multi-turn**, and the Batches API has no multi-turn -- so the
format failures are retried **synchronously** after the batch returns. "Batch the
bulk, sync the retries." The rule is in `batch.py` (`recommend_mode`).

## Module guide

| Module                | Responsibility                                                                                                                                  |
| --------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------- |
| `schemas.py`          | `ExtractionRecord` -- the four field kinds; the trap field is required+nullable                                                                 |
| `tool.py`             | The `extract` tool's JSON schema + `tool_choice`; the syntax/semantics statement                                                                |
| `risk.py`             | Categorical RISK criteria + anchored severity (deterministic comparisons)                                                                       |
| `few_shot.py`         | The few-shot block: a reasoning trace and a negative (silent->null) example                                                                     |
| `validator.py`        | FORMAT validation (retryable) vs SUPPORT check (escalate, never retry)                                                                          |
| `retry.py`            | Bounded retry over format failures, carrying the exact constraint                                                                               |
| `extractor.py`        | `ExtractorClient` seam + `ScriptedExtractor` (replays attempts, drives retries)                                                                 |
| `reviewer.py`         | `ReviewerClient` seam + `ScriptedReviewer` -- a fresh instance, no shared context                                                               |
| `routing.py`          | Route on agreement: agree / disagree / unsupported                                                                                              |
| `pipeline.py`         | Per-document and batch orchestration; `PipelineResult` carries every step (a retry-exhausted document escalates rather than aborting the batch) |
| `batch.py`            | The batch-vs-synchronous decision and its no-multi-turn consequence                                                                             |
| `sample_documents.py` | 10 documents incl. the fabrication trap, and the fabricating distractor                                                                         |
| `live.py`             | Optional `ClaudeExtractor` (forced tool) / `ClaudeReviewer` against the real API                                                                |
| `demo.py`             | The two-trajectory offline demonstration                                                                                                        |

## The live path (optional)

```bash
poetry install --with dev --with live
export ANTHROPIC_API_KEY=...               # or cp .env.example .env
```

`ClaudeExtractor` forces the `extract` tool and ships the few-shot block in its
system prompt; `ClaudeReviewer` is a separate call with no extractor context, so
it is a genuinely independent instance. Both run against `claude-opus-4-8`.
Thinking is deliberately off: a named `tool_choice` forces tool use, which the
API rejects alongside extended/adaptive thinking -- and the exercise requires the
forced tool, so consistency comes from the schema and few-shot block, not
reasoning depth. The deterministic seam (`ScriptedExtractor` + `ScriptedReviewer`)
powers every test, so the suite never needs a key.
