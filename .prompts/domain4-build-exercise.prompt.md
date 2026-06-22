# Domain 4 Build Exercise — Document Extraction Pipeline

You are helping me build a document-extraction pipeline that exercises every concept in
Domain 4 (Prompt Engineering & Structured Output) of the Claude Certified Architect exam.
Build it with me incrementally. Explain each design choice as you go, and push back hard if
my instructions violate the principles below.

## Build target

An **extraction pipeline** that reads vendor contracts and emits one structured record per
document. It must run over a **batch of 10 sample documents**, force its output through a
**tool_use JSON schema**, classify findings against **explicit categorical criteria**, retry
**format** failures, and verify results with an **independent reviewer pass**. Among the 10
documents, **at least one is deliberately silent** on a field the schema wants (e.g. it never
states a governing law or a delivery date).

The test the pipeline must pass:

> The **fabrication-trap document** -- the one that never states its governing law -- must come
> back as `NOT_SPECIFIED` (or `null`), **never** a guessed jurisdiction. If any field is filled
> with a value that does not actually appear in that document's text, the pipeline fails the
> test. Truthful absence must survive end to end.

## Requirements -- every one must be satisfied

1. **The extraction tool + JSON schema, forced via `tool_choice`.** Define one `extract` tool
   whose input schema demonstrates all four field kinds, and force it (named `tool_choice`, not
   `auto`) so every call returns this shape:
   - **Required** fields (must always be present -- e.g. `document_id`, `vendor_name`).
   - **Optional** fields (may be omitted entirely).
   - **Nullable** fields (present but legitimately `null` when the source is silent -- this is the
     truthful escape hatch the fabrication-trap document depends on).
   - **Enums**, including a **`NOT_SPECIFIED`** (or `UNCLEAR`) member for "the document doesn't
     say," and an **`other` + detail-string** pair for the long tail (e.g.
     `category: [...,"other"]` with a nullable `category_detail`).
     State plainly what forcing the tool **does** guarantee (syntax: valid JSON, right types,
     enums in range, required present) and what it **does not** (semantics: the value can still
     be wrong). Explain why a `required` field with no nullable/`NOT_SPECIFIED` option is what
     _causes_ fabrication on the trap document.

2. **Explicit categorical criteria + severity calibration -- no confidence words.** The pipeline
   flags risky clauses. Define the flag by **categorical membership**, not self-reported
   confidence:
   - A clause is a `RISK` only if it meets a named criterion (e.g. liability cap > $1,000,000,
     OR indemnification uncapped, OR governing law outside an allowed set) -- not "if the model is
     confident it's risky."
   - A **severity enum** (`CRITICAL` / `WARNING` / `INFO`) where **each level carries an anchoring
     example**, so the level is a definition, not a vibe.
     Explain the false-positive trust problem: why a gate built on "high confidence" passes
     fluent hallucinations, and why a numeric `1-10` scale without anchors just relocates the
     vagueness into the number.

3. **Few-shot examples with reasoning -- covering edges, not the easy case.** Supply the few-shot
   block that ships with the extraction prompt. It must:
   - Include **at least one example that shows a reasoning trace** (not bare input->output) for a
     genuinely confusable case -- e.g. distinguishing a "2% discount if paid in 10 days" early-pay
     discount from the net payment term, so both land in distinct fields.
   - Include **at least one negative example** (an input that should produce _no_ finding /
     `null` / `NOT_SPECIFIED`) so "don't fabricate" is demonstrated, not just stated.
   - Be **mutually consistent** -- explain why a contradiction across examples is worse than no
     examples at all.
     Justify why few-shot is the _first_ lever for output consistency, ahead of longer
     instructions or louder emphasis.

4. **Validation-retry loop -- format yes, missing data never.** Wrap the call in a validator and
   a bounded retry:
   - On a **format/constraint failure** (bad enum, missing required field, out-of-range value),
     send the model its **exact error text** and ask for a correction. Show the retry message
     carrying the specific violated constraint, not "try again." Cap retries (e.g. 2-3) then
     escalate.
   - **Do NOT retry a missing-source-data failure.** Explain that retrying "you didn't provide
     `governing_law`" pressures the model to invent one -- the trap. That case is handled by the
     nullable field from Requirement 1, not by the loop.
   - Add a **`detected_pattern`** field to the schema (e.g. `"matched literal '$1,000,000' in
clause 7.2"`) and show the validator **programmatically checking** that the cited pattern
     actually appears in the source text -- catching a fabrication a bare value would hide.

5. **Independent reviewer pass + the batch decision.** Verify and route:
   - Run a **second, independent instance** (a reviewer with no memory of the extractor's
     reasoning) over each record + its source. Explain the self-review limitation: why "now review
     your own answer" in the same context rationalizes rather than catches.
   - **Confidence-based routing** on the result: extractor and reviewer **agree** -> auto-accept;
     **disagree** -> route to human; reviewer flags an unsupported value -> escalate. Make explicit
     that the trustworthy "confidence" signal is **agreement between independent instances**, not a
     single model's confidence word (the Requirement 2 trap).
   - State the **batch decision** for these 10 documents and the rule behind it: synchronous when
     something is waiting / a step is chained on the result; the **Batches API** (~50% cheaper,
     up to a 24-hour window, **no multi-turn**) when volume is high and nothing is blocked. Note
     the consequence: because batch is no-multi-turn, the **validation-retry loop cannot run inside
     a batch** -- the common shape is batch the bulk extraction, then synchronously retry the
     failures.

## Principles to enforce while building (Domain 4 spine)

- **Define what counts, never ask how confident.** Categorical criteria are reproducible and
  auditable; self-reported confidence has no reliable mapping to correctness, so any gate built on
  it passes confident hallucinations. A numeric scale without anchoring examples is the same
  vagueness wearing a number.
- **Few-shot is the first lever for consistency.** More effective than longer instructions or
  emphasis. Show reasoning to teach judgment, cover the boundary and edge cases (not the easy
  case), include negatives, and keep examples mutually consistent.
- **Forcing the tool guarantees syntax, never semantics.** A schema-valid response can still hold
  the wrong value. Structure stops malformed JSON; it does not stop a confident wrong number.
- **Give a truthful option for every case, or the model fabricates.** Nullable fields,
  `NOT_SPECIFIED` enum members, and `other`+detail exist so the model never has to invent a value
  to satisfy `required`. Absence must be representable.
- **Retry format errors; never retry missing data.** The error text is what makes a retry work --
  feed the exact violated constraint back. But you cannot retry your way to data that isn't in the
  source; that path fabricates. Handle absence with a nullable field, not a loop. Make outputs
  checkable with `detected_pattern`.
- **Independent instances beat self-review.** A model reviewing its own output in-context
  rationalizes its prior reasoning. A fresh reviewer evaluates the artifact adversarially.
  Legitimate confidence is _agreement between independent passes_, not a self-reported word.
- **Batch when nothing is waiting.** ~50% cost for a 24-hour, no-multi-turn window. Synchronous
  when latency matters or a step is chained. Batch can't run an inline retry loop -- retry the
  failures synchronously afterward.

## Deliverables

Produce, with the design explained:

1. The `extract` tool's full JSON input schema -- showing required, optional, nullable, and enum
   fields (including `NOT_SPECIFIED` and `other`+detail) -- plus the `tool_choice` setting that
   forces it, with the syntax-guaranteed / semantics-not statement.
2. The categorical `RISK` criterion and the severity enum with an anchoring example per level,
   plus the one-paragraph false-positive-trust explanation.
3. The few-shot block: one reasoning-trace example for a confusable case and one negative example,
   with the consistency justification.
4. The validation-retry logic: the format-error retry message (carrying the exact constraint),
   the explicit no-retry-on-missing-data path, and the `detected_pattern` check against source
   text. Pseudocode is fine -- architecture over syntax.
5. The reviewer pass + routing table (agree / disagree / unsupported), and the batch-vs-synchronous
   decision for the 10 documents with the rule stated.
6. One paragraph: walk the **fabrication-trap document** (silent on governing law) through the
   pipeline and show that it ends as `NOT_SPECIFIED`/`null` at every stage -- schema, retry,
   reviewer -- naming exactly which mechanism prevents the guess at each step.

## How I want you to grade the result (apply this to your own output)

- Does the trap document survive as `NOT_SPECIFIED`/`null` end to end, with **no fabricated**
  field anywhere in the 10 records?
- Is every flag defined by **categorical criteria** (not confidence), and does each severity level
  carry an **anchoring example**?
- Does the schema actually demonstrate all four field kinds, and is the **syntax-yes /
  semantics-no** distinction stated correctly?
- Does the retry feed the **exact error** and fire only on **format** failures -- explicitly never
  on missing source data -- and does `detected_pattern` get checked against the source?
- Is the reviewer a **genuinely independent instance**, and is routing driven by **agreement**
  rather than a self-reported confidence word?
- Is the **batch-vs-synchronous** call correct for these 10 docs, with the no-multi-turn
  consequence for the retry loop acknowledged?

Build it step by step. Where my instructions would violate a principle above, stop and tell me.
