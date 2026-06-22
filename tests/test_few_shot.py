"""The few-shot block teaches judgment on the boundary, and demonstrates absence.

Few-shot is the first lever for output consistency -- more effective than longer
instructions or louder emphasis, because the model pattern-matches examples more
reliably than it follows prose. So the examples must cover the confusable cases,
not the easy one, and they must be mutually consistent: a contradiction across
examples is worse than no examples, because it teaches the mapping is arbitrary
and *raises* variance instead of lowering it.

The block carries (1) a reasoning-trace example for a genuinely confusable case
(early-pay discount vs net payment term) and (2) a negative example where the
truthful output is null/NOT_SPECIFIED. These tests pin both, and confirm every
example output is itself schema-valid (an inconsistent example would mislead).
"""

from contract_extraction.few_shot import FEW_SHOT_EXAMPLES, render_few_shot
from contract_extraction.validator import check_support, validate_format


def test_every_example_output_is_schema_valid():
    # An example that did not itself validate would teach the model a shape the
    # tool rejects -- the contradiction the consistency rule forbids.
    for example in FEW_SHOT_EXAMPLES:
        record, errors = validate_format(example["output"])
        assert errors == [], f"{example['name']}: {errors}"
        assert record is not None


def test_every_example_is_grounded_in_its_own_source():
    # The examples teach grounding by imitation, so each example's own cited
    # literals must appear verbatim in its own source -- otherwise the block
    # demonstrates the exact ungrounded-citation the support check rejects.
    for example in FEW_SHOT_EXAMPLES:
        record, _ = validate_format(example["output"])
        support_errors = check_support(record, example["source"])
        assert support_errors == [], f"{example['name']}: {support_errors}"


def test_reasoning_example_separates_discount_from_net_term():
    example = next(e for e in FEW_SHOT_EXAMPLES if e["name"] == "discount_vs_net_term")
    record, _ = validate_format(example["output"])
    assert record.net_payment_days == 30
    assert record.early_pay_discount is not None
    assert record.early_pay_discount.percent == 2
    assert record.early_pay_discount.within_days == 10
    # It must carry a reasoning trace, not a bare input->output mapping.
    assert example["reasoning"].strip()


def test_negative_example_shows_truthful_absence():
    example = next(e for e in FEW_SHOT_EXAMPLES if e["name"] == "silent_governing_law")
    record, _ = validate_format(example["output"])
    assert record.governing_law is None
    # No detected_pattern is fabricated for a field with no supporting text.
    assert all(p.field != "governing_law" for p in record.detected_patterns)


def test_rendered_block_includes_reasoning_and_both_examples():
    rendered = render_few_shot()
    assert "discount" in rendered.lower()
    assert "null" in rendered.lower()
    for example in FEW_SHOT_EXAMPLES:
        assert example["reasoning"] in rendered
