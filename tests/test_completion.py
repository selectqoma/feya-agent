from decimal import Decimal

import pytest

from feya.completion import calculate, validate_completion
from feya.conversation_models import CompletionReview, WorkSource

SOURCE = WorkSource(id="src_quote", title="Quote", content="Unit price EUR 100. Need 10 units.")
CANDIDATE = "Quoted price EUR 100 [src_quote]. Total: 100 * 10 = 1000 EUR."
CRITERIA = ["Calculate total quoted cost for ten units and cite the quote."]


def review(**changes):
    return CompletionReview.model_validate({
        "criteria": [{"criterion_index": 0, "passed": True, "reason": "Total and source present."}],
        "evidence": [{"source_id": "src_quote", "quote": "Unit price EUR 100.",
                      "claim": "Quoted price EUR 100"}],
        "calculations": [{"expression": "100 * 10", "result": "1000"}],
        **changes,
    })


def test_valid_report_has_review_and_deterministic_checks_but_only_draft_label():
    result = validate_completion(CANDIDATE, CRITERIA, [SOURCE], review())
    assert result["passed"] and result["label"] == "draft_prepared"
    assert all(check["passed"] for check in result["checks"])
    assert "factual certification" in str(result)


@pytest.mark.parametrize("bad_review", [
    review(criteria=[]),
    review(criteria=[{"criterion_index": 0, "passed": True, "reason": "Fine"}] * 2),
    review(criteria=[{"criterion_index": 1, "passed": True, "reason": "Wrong criterion"}]),
    review(criteria=[{"criterion_index": 0, "passed": False, "reason": "Missing work"}]),
    review(evidence=[{"source_id": "src_missing", "quote": "Unit price EUR 100.", "claim": "Quoted price EUR 100"}]),
    review(calculations=[]),
    review(calculations=[{"expression": "100 * 10", "result": "999"}]),
    review(unsupported_claims=["The report promises free delivery without evidence."]),
])
def test_incomplete_or_unfounded_review_blocks_completion(bad_review):
    result = validate_completion(CANDIDATE, CRITERIA, [SOURCE], bad_review)
    assert not result["passed"] and result["label"] == "needs_revision"


def test_unknown_inline_citation_and_empty_artifact_are_rejected():
    assert not validate_completion(CANDIDATE + " [src_fake]", CRITERIA, [SOURCE], review())["passed"]
    assert not validate_completion(" ", CRITERIA, [SOURCE], review())["passed"]


def test_false_arithmetic_fails_even_if_reviewer_marks_every_criterion_passed():
    candidate = CANDIDATE.replace("1000", "999")
    result = validate_completion(candidate, CRITERIA, [SOURCE], review(
        calculations=[{"expression": "100 * 10", "result": "999"}],
    ))
    assert not result["passed"]
    assert not next(check for check in result["checks"] if check["name"] == "calculation_0")["passed"]


def test_calculation_result_must_appear_in_artifact_not_just_citation_id():
    assert not validate_completion("Quoted price EUR 100 [src_quote]", CRITERIA, [SOURCE], review())["passed"]
    candidate = "Result [src_1000]"
    result = validate_completion(candidate, ["Show result"], [], CompletionReview(
        criteria=[{"criterion_index": 0, "passed": True, "reason": "Present"}],
        calculations=[{"expression": "100 * 10", "result": "1000"}],
    ))
    assert not next(check for check in result["checks"] if check["name"] == "calculation_0")["passed"]


def test_decimal_math_is_exact_and_formatted_totals_are_supported():
    assert calculate("0.1 + 0.2") == Decimal("0.3")
    assert calculate("(100 + 40) * 10 / 2") == Decimal("700")
    assert calculate("-10 + +4") == Decimal("-6")
    assert validate_completion(CANDIDATE.replace("1000", "1,000"), CRITERIA, [SOURCE], review())["passed"]
    assert validate_completion(CANDIDATE.replace("1000 EUR", "EUR 1,000"), CRITERIA, [SOURCE], review())["passed"]
    assert not validate_completion(CANDIDATE.replace("1000 EUR", "EUR 1,000"), CRITERIA, [SOURCE], review(calculations=[]))["passed"]


def test_checked_markdown_items_are_not_mistaken_for_unknown_citations():
    assert validate_completion("- [x] Done\n" + CANDIDATE, CRITERIA, [SOURCE], review())["passed"]
    assert not validate_completion("[x] is an actual citation\n" + CANDIDATE, CRITERIA, [SOURCE], review())["passed"]


def test_explicit_rounding_uses_half_up_and_preserves_exact_default():
    candidate = "100 / 3 = 33.33, rounded to 2 decimal places."
    criteria = ["Calculate rounded share"]
    rounded = CompletionReview(criteria=[{"criterion_index": 0, "passed": True, "reason": "Rounded share present"}],
                               calculations=[{"expression": "100 / 3", "result": "33.33", "decimal_places": 2}])
    assert validate_completion(candidate, criteria, [], rounded)["passed"]
    rounded.calculations[0].decimal_places = None
    assert not validate_completion(candidate, criteria, [], rounded)["passed"]
    rounded.calculations[0].expression = "1.005 + 0"
    rounded.calculations[0].result = "1.01"
    rounded.calculations[0].decimal_places = 2
    assert validate_completion("1.005 + 0 = 1.01, rounded to 2 decimal places.", criteria, [], rounded)["passed"]


@pytest.mark.parametrize("expression", [
    "__import__('os').system('whoami')", "2 ** 100", "1 / 0", "True + 1", "1e100",
    "10 % 3", "x + 2", "1 + " * 50 + "1", "9" * 100, "[1][0]", "float('nan')",
])
def test_unsafe_or_unbounded_calculations_are_rejected(expression):
    with pytest.raises(ValueError):
        calculate(expression)


@pytest.mark.parametrize("evidence", [
    [],
    [{"source_id": "src_quote", "quote": "Unit price: EUR 100", "claim": "Quoted price EUR 100"}],
    [{"source_id": "src_quote", "quote": "Unit price EUR 100.", "claim": "**Quoted price EUR 100**"}],
])
def test_excerpt_matching_is_advisory_when_agent_accepts_substance(evidence):
    checked = validate_completion(CANDIDATE, CRITERIA, [SOURCE], review(evidence=evidence))
    assert checked["passed"]
    notes = [item for item in checked["checks"] if not item["passed"]]
    assert notes and all(item["blocking"] is False for item in notes)
