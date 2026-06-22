# Domain 4 Build Exercise -- Document Extraction Pipeline

## Prompt

See [build prompt](../.prompts/domain4-build-exercise.prompt.md).

## Response

The implementation is in [`../domain4-extraction-pipeline/`](../domain4-extraction-pipeline/):
the forced `extract` tool is plain Messages-API tool use (`tools=[extract]`,
`tool_choice={"type":"tool","name":"extract"}`), and the retry/reviewer/routing
pieces are deterministic code wrapped around it. Every component is test-driven
and runs offline against a scripted seam.

One thing up front, because you asked me to push back where your instructions
would force a principle violation: **your spec doesn't.** It is internally
consistent and aligned with its own Domain 4 spine. There is exactly one
_refinement_ I carried over from the Domain 1 build, flagged here so it doesn't
read as a quiet redesign: **the `RISK` threshold comparison is deterministic
code, not the model's call.** Your Requirement 2 already frames `RISK` as
categorical membership ("liability cap > $1,000,000"); I implemented the
consequence -- the model supplies the fields and the semantic call, and Python
does `cap > 1_000_000` and the severity assignment. Letting an LLM decide whether
`5,000,000 > 1,000,000` is the "define what counts, never ask how confident"
mistake wearing a number.

Here are the six deliverables.

---

## 1. The `extract` tool, forced via `tool_choice`

The tool is forced (`tool_choice={"type":"tool","name":"extract"}`) so every call
returns the `extract` shape -- never free text, never a different tool. The input
schema demonstrates all four field kinds (`schemas.py`, `tool.py`):

```text
extract.input_schema = {
  type: "object",
  properties: {
    # Required + non-null -- always present.
    document_id:          { type: "string" },
    vendor_name:          { type: "string" },

    # Optional -- declared, but absent from `required`, so it may be omitted.
    vendor_contact_email: { type: ["string","null"] },

    # Nullable + required-present -- the model must address these; null is the
    # truthful "the document is silent" value.
    governing_law:        { type: ["string","null"] },
    delivery_date:        { type: ["string","null"] },
    net_payment_days:     { type: ["integer","null"] },
    early_pay_discount:   { type: ["object","null"], ... },
    liability_cap_usd:    { type: ["number","null"] },

    # Enums -- including NOT_SPECIFIED and the other+detail pair.
    indemnification:      { enum: ["capped","uncapped","none","NOT_SPECIFIED"] },
    category:             { enum: ["services","goods","license","nda","other"] },
    category_detail:      { type: ["string","null"] },   # required iff category=="other"

    detected_patterns:    [ { field, literal } ],         # checkable provenance
  },
  required: [document_id, vendor_name, governing_law, delivery_date,
             net_payment_days, early_pay_discount, liability_cap_usd,
             indemnification, category, category_detail, detected_patterns],
}
```

**Syntax-yes / semantics-no.** Forcing the tool guarantees _syntax_: valid JSON,
declared types, enums in range, required keys present. It guarantees nothing about
_semantics_ -- a schema-valid record can still name the wrong governing law or the
wrong cap. Structure stops malformed JSON; it does not stop a confident wrong
value.

**Why a `required` field with no escape hatch causes fabrication.** If
`governing_law` were `required` and non-nullable, the model would have to emit a
string to satisfy the schema -- so on a silent document it invents one. The fix is
not to drop it from `required` (then the model dodges by omitting it); it is to
keep it required-to-be-_present_ and make its type admit `null`. The model must
address the field, and `null` is the truthful way to. `NOT_SPECIFIED` (on
`indemnification`) and `other`+`category_detail` are the same idea for enums: a
named "the document doesn't say" member and a long-tail escape, so the model never
has to mis-bucket a value to satisfy the type.

---

## 2. Categorical `RISK` criterion + anchored severity

A record is flagged **only** when it meets a named criterion computed from the
extracted fields (`risk.py`) -- never "if the model is confident it's risky":

```text
RISK if any of:
  indemnification == "uncapped"                          -> CRITICAL
  liability_cap_usd is not None and > 1,000,000          -> WARNING
  governing_law is not None and not in {DE, NY, CA}      -> INFO
```

Each severity level carries an **anchoring example**, so the level is a definition
rather than a vibe:

- **CRITICAL** -- unbounded exposure. Anchor: indemnification `uncapped`
  (e.g. "Vendor's indemnification obligations are unlimited and uncapped").
- **WARNING** -- bounded but large exposure. Anchor: a liability cap of
  `$5,000,000` (> the `$1,000,000` threshold).
- **INFO** -- a fact worth a human glance. Anchor: governing law `Cayman Islands`
  (outside the allowed `{Delaware, New York, California}` set).

**The false-positive trust problem.** A gate built on "high confidence" passes
fluent hallucinations: a model's self-reported confidence has no reliable mapping
to correctness, so a confident _wrong_ value clears the gate exactly as a
confident right one does -- you have gated on fluency, not truth. A numeric `1-10`
scale without anchors does not fix this; it relocates the vagueness into the number
(one run's "7" is another run's "4"). Categorical membership is reproducible and
auditable: the same fields always produce the same flag, and any reviewer can
check the rule. The threshold comparison itself is deterministic code; the model
never decides `> 1,000,000`.

Note this is also why truthful absence never produces a false positive: a `null`
governing law is _not_ "outside the allowed set" -- it is the absence of a value,
so no criterion fires.

---

## 3. The few-shot block -- reasoning trace + negative example

The block ships in the extractor's system prompt (`few_shot.py`,
`live.EXTRACTOR_SYSTEM`). It carries two examples that cover the boundary, not the
easy case:

**Reasoning-trace example (a genuinely confusable case).** Telling an early-pay
discount apart from the net payment term:

```text
SOURCE: "Invoices are payable net 30 days. A 2% discount applies if payment is
         received within 10 days of the invoice date."
REASONING: Two distinct terms, not one. "net 30 days" is the net window
   (net_payment_days = 30). The "2% ... within 10 days" is a separate incentive
   (early_pay_discount = {percent: 2, within_days: 10}). Merging them would drop
   the discount; putting 10 into net_payment_days would misstate the due date.
EXTRACT: { net_payment_days: 30, early_pay_discount: {percent: 2, within_days: 10}, ... }
```

**Negative example (demonstrates "don't fabricate").** A document silent on
governing law maps to `null`, with no fabricated `detected_pattern`:

```text
SOURCE: "Order Form -- Vendor: Example Vendor. ...states the service category,
         but says nothing about which jurisdiction's law governs."
REASONING: The document never states a governing law. The truthful output is
   governing_law = null -- not a guessed jurisdiction, and no governing_law
   detected_pattern, because there is no supporting text to cite. The vendor name
   IS in the source, so it carries a grounded citation.
EXTRACT: { governing_law: null,
           detected_patterns: [ {field: "vendor_name", literal: "Example Vendor"} ] }
```

**Why mutual consistency matters more than coverage.** A contradiction across
examples is worse than no examples. Few-shot works by pattern induction: two
examples mapping the same situation to different outputs teach the model that the
mapping is arbitrary, which _raises_ variance instead of lowering it. With no
examples the model at least falls back consistently on the instructions. So every
example output here is itself schema-valid (tested in `test_few_shot.py`) and none
contradicts another.

**Why few-shot is the first lever.** It is more effective for output consistency
than longer instructions or louder emphasis, because the model imitates concrete
examples more reliably than it parses prose rules. Reach for examples before you
reach for more words.

---

## 4. The validation-retry loop -- format yes, missing data never

Validation has two categories, handled oppositely (`validator.py`, `retry.py`):

```text
extract_with_retry(client, document, max_attempts=3):
    prior_error = None
    for _ in range(max_attempts):
        raw = client.extract(document, prior_error=prior_error)
        record, format_errors = validate_format(raw)     # pydantic: shape/enum/range
        if not format_errors:
            return record
        prior_error = format_retry_message(format_errors) # carries the EXACT constraint
    raise FormatRetryExhaustedError(...)                   # escalate after the cap
```

When the cap is reached, `run_document` catches the exhaustion and returns an
**ESCALATE** result carrying the reason -- a document the model can never format
is a human-review case, not a batch-killing exception. So one unrecoverable
document in a batch escalates on its own while the rest still return their
results.

**The retry carries the exact violated constraint, not "try again":**

```text
"Your previous extraction failed validation on these exact constraints:
 - indemnification: input should be 'capped','uncapped','none' or 'NOT_SPECIFIED'
 Return the extract tool again, correcting only these fields. Do not invent values
 to satisfy a constraint -- use null or NOT_SPECIFIED where the document is silent."
```

**No retry on missing source data -- by construction.** There is no retry path for
absence: a silent field is `null`, `null` is format-valid, so it returns on the
first attempt. Pushing "you didn't provide governing_law" back at the model is what
manufactures a fabricated jurisdiction. Absence is handled by the nullable field
from Deliverable 1, not by this loop.

**`detected_pattern` checked against the source.** Each record carries
`detected_patterns: [{field, literal}]`, and `check_support` verifies every
`literal` is a non-empty verbatim substring of the source text -- catching a
_miscited_ fabrication a bare value would hide. The boundary is worth stating
plainly: this validates cited provenance, so a fabrication that omits its
citation entirely slips past `check_support` and is caught only by the
independent reviewer (Deliverable 5) -- the two are complementary, not redundant.
A support failure is **not** a format failure: it is never retried (retrying
"your value isn't in the source" only pressures a better disguise); it is routed
to escalation in Deliverable 5.

---

## 5. Independent reviewer pass + the batch decision

**A second, independent instance** reviews each record (`reviewer.py`,
`live.ClaudeReviewer`). It is handed only the finished record and the source
document -- never the extractor's reasoning or message history. "Now review your
own answer" in the same context rationalizes the prior reasoning rather than
catching it, because the model is defending a conclusion it already committed to.
A fresh instance has nothing to defend and can disagree.

**Confidence-based routing -- where "confidence" means inter-instance agreement**
(`routing.py`):

| Signal                                                              | Route          |
| ------------------------------------------------------------------- | -------------- |
| Reviewer agrees, no unsupported value (either pass)                 | `AUTO_ACCEPT`  |
| Reviewer disagrees (on a supported value)                           | `HUMAN_REVIEW` |
| Reviewer flags an unsupported value, **or** the support check fails | `ESCALATE`     |

The trustworthy signal is agreement between two instances that never shared
context -- not a single model's self-reported confidence word (the Deliverable 2
trap). The programmatic support check is not overruled by a reviewer that happened
to agree: an unsupported value from _either_ source escalates.

**The batch decision for these 10 documents** (`batch.py`). Synchronous when
something is waiting on the result or a step is chained on it. The Batches API
(~50% cheaper, up to a 24-hour window, **no multi-turn**) when volume is high and
nothing is blocked. Here nothing is waiting and each extraction is a single
forced-tool call, so the **bulk extraction batches**. But the **retry loop is
multi-turn**, and batch has no multi-turn -- so the **validation-retry loop cannot
run inside a batch**. The shape that falls out: batch the bulk extraction, then
retry the format failures **synchronously** afterward. "Batch the bulk, sync the
retries."

---

## 6. The fabrication-trap document, walked end to end

doc-07 (Wayne Enterprises) never states a governing law. Here is `null` surviving
every stage, with the exact mechanism at each step:

- **Schema.** `governing_law` is `required`-to-be-present and nullable, so the
  model emits `governing_law: null` -- it is not forced to invent a string to
  satisfy `required`, and it cannot dodge by omitting the key. _Mechanism: the
  nullable escape hatch._
- **Retry.** `null` is format-valid, so `validate_format` passes on the first
  attempt and the retry loop never fires. There is no "you didn't provide
  governing*law" message to pressure a guess. \_Mechanism: format-only retry; absence
  is never a retry case.*
- **Support check.** The honest record cites no `detected_pattern` for
  `governing_law` (there is no source text to quote), so `check_support` finds
  nothing to reject. _Mechanism: nothing fabricated, nothing to catch._
- **Risk.** A `null` governing law is not "outside the allowed set," so no
  criterion fires and no false-positive flag appears. _Mechanism: categorical
  criteria over a value's presence, not its absence._
- **Reviewer + routing.** The independent reviewer, seeing the record and the
  source, agrees the `null` is correct (nothing in the source states a
  jurisdiction), so the record `AUTO_ACCEPT`s with `governing_law = null`.
  _Mechanism: agreement between independent instances._

And the defended distractor: a fabricating extraction that guesses `"Delaware"`
cites the literal `"governed by Delaware law"`, which is **not** in doc-07's
source. `check_support` flags it (`UNSUPPORTED`, never retried) and the reviewer
independently flags `governing_law` -- either signal routes the record to
`ESCALATE`. The guess never auto-accepts. (`test_pipeline.py::
test_fabricating_extractor_on_the_trap_is_caught_and_escalated`.)

---

## Self-grade against your rubric

- **Trap survives as `null` end to end, no fabricated field in the 10 records?**
  Yes. `test_trap_document_stays_not_specified_end_to_end` asserts `governing_law
is None` through the pipeline; `test_no_fabricated_field_across_all_ten_records`
  asserts every `detected_pattern` literal is a verbatim source substring across
  all 10 and the trap stays `null`. The fabricating distractor is caught and
  escalated.
- **Every flag categorical, each severity anchored?** Yes. `risk.assess_risk` uses
  named criteria over extracted fields with deterministic comparisons; CRITICAL /
  WARNING / INFO each carry an anchoring example. No confidence word anywhere.
- **All four field kinds, syntax-yes/semantics-no stated?** Yes. Required,
  optional, nullable, and enum (incl. `NOT_SPECIFIED` and `other`+detail) are
  distinct in `schemas.py`/`tool.py`, and the guarantee/limit is stated in
  `tool.py` and above.
- **Retry feeds the exact error, fires only on format, never on missing data, and
  `detected_pattern` is checked against source?** Yes. `format_retry_message`
  carries the exact constraint; `retry.py` only loops on `validate_format`
  failures; absence is `null` (format-valid, never retried); `check_support`
  verifies the cited literal against the source.
- **Reviewer genuinely independent, routing on agreement?** Yes.
  `ClaudeReviewer` is a separate call given only record + source; `route` keys off
  reviewer agreement and the support check, not a self-reported confidence.
- **Batch-vs-sync correct, no-multi-turn consequence acknowledged?** Yes. Bulk
  extraction batches (nothing waiting); the multi-turn retry loop runs
  synchronously afterward, because batch has no multi-turn. Stated in `batch.py`
  and `test_batch.py::test_the_ten_document_decision`.

The one deviation from a literal reading of the spec -- moving the `> $1M`
comparison into deterministic code -- is in Deliverable 2 with rationale. If you
want the LLM to own the comparison too (e.g. because real caps are often prose like
"the fees paid in the trailing 12 months" with no clean number), say so and I'll
show the hybrid: deterministic compare for numeric caps, a subagent interpretation
pass for formula caps, with the risk flag keyed to whichever path produced the
value.
