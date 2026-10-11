"""Deterministic checks around a model's review, not factual certification."""

import ast
import re
from decimal import ROUND_HALF_UP, Decimal, DecimalException, localcontext

from feya.conversation_models import CompletionReview, WorkSource

CITATION = re.compile(r"\[([a-zA-Z0-9_.:-]+)\](?!\()")
NUMBER = re.compile(r"(?<![\d.])[+-]?(?:\d{1,3}(?:,\d{3})+|\d+)(?:\.\d+)?(?!\d|\.\d)")
EQUATION = re.compile(r"(?<![\w.])([+-]?\d+(?:\.\d+)?(?:\s*[+*/-]\s*[+-]?\d+(?:\.\d+)?)+)\s*=\s*(?:[A-Z]{3}\s+|[$€£])?([+-]?\d+(?:\.\d+)?)")


def calculate(expression: str) -> Decimal:
    """Evaluate only bounded decimal literals and elementary arithmetic."""
    if not expression or len(expression) > 128:
        raise ValueError("Calculation expression is empty or too long")
    try:
        tree = ast.parse(expression, mode="eval")
        if len(list(ast.walk(tree))) > 40:
            raise ValueError("Calculation has too many operations")

        def value(node):
            if isinstance(node, ast.Constant) and type(node.value) in {int, float}:
                literal = ast.get_source_segment(expression, node)
                if literal is None or not re.fullmatch(r"\d+(?:\.\d+)?", literal):
                    raise ValueError("Use decimal literals without exponent notation")
                result = Decimal(literal)
            elif isinstance(node, ast.UnaryOp) and isinstance(node.op, (ast.UAdd, ast.USub)):
                result = value(node.operand) * (-1 if isinstance(node.op, ast.USub) else 1)
            elif isinstance(node, ast.BinOp) and isinstance(node.op, (ast.Add, ast.Sub, ast.Mult, ast.Div)):
                left, right = value(node.left), value(node.right)
                if isinstance(node.op, ast.Add):
                    result = left + right
                elif isinstance(node.op, ast.Sub):
                    result = left - right
                elif isinstance(node.op, ast.Mult):
                    result = left * right
                else:
                    result = left / right
            else:
                raise ValueError("Only decimal arithmetic with +, -, *, / and parentheses is allowed")
            if not result.is_finite() or abs(result) > Decimal("1e24"):
                raise ValueError("Calculation is outside the supported numeric range")
            return result

        with localcontext() as context:
            context.prec = 50
            return value(tree.body)
    except (SyntaxError, DecimalException, RecursionError) as exc:
        raise ValueError("Invalid decimal calculation") from exc


def validate_completion(candidate: str, criteria: list[str], sources: list, review) -> dict:
    review = CompletionReview.model_validate(review)
    sources = [WorkSource.model_validate(source) for source in sources]
    checks = []

    def check(name, passed, detail):
        checks.append({"name": name, "passed": bool(passed), "detail": detail})

    check("artifact_present", bool(candidate.strip()), "A nonempty candidate artifact is required.")
    indexes = [item.criterion_index for item in review.criteria]
    check("criteria_coverage", bool(criteria) and sorted(indexes) == list(range(len(criteria))),
          "The reviewer must assess each acceptance criterion exactly once.")
    for item in review.criteria:
        check(f"criterion_{item.criterion_index}", item.passed,
              "Model review of acceptance criterion: " + item.reason)
    check("unsupported_claims", not review.unsupported_claims,
          "; ".join(review.unsupported_claims) or "The reviewer reported no unsupported claims; this is not factual certification.")

    source_map = {source.id: source.content for source in sources}
    citation_text = re.sub(r"(?m)^(\s*[-*+]\s+)\[[xX ]\]", r"\1", candidate)
    cited = set(CITATION.findall(citation_text))
    check("citation_ids", cited <= source_map.keys(),
          "Inline citations must refer to sources supplied to this task.")
    supported = set()
    for index, evidence in enumerate(review.evidence):
        valid = (evidence.source_id in source_map
                 and evidence.quote.strip() and evidence.quote in source_map[evidence.source_id]
                 and evidence.claim.strip().rstrip(".!?")
                 and evidence.claim.strip().rstrip(".!?") in candidate
                 and evidence.source_id in cited)
        check(f"evidence_{index}", valid,
              "The quote must occur literally in its source and the claim excerpt in the artifact (terminal sentence punctuation may differ); entailment remains a model assessment.")
        if valid:
            supported.add(evidence.source_id)
    check("citation_evidence", cited <= supported and (not sources or bool(supported)),
          "Each cited source needs a checked literal quote and artifact claim; source-based work needs evidence.")

    # Strip citation identifiers so a source's numeric ID cannot satisfy a calculated result.
    without_citations = CITATION.sub("", candidate)
    numbers = {Decimal(token.replace(",", "")) for token in NUMBER.findall(without_citations)}
    reviewed = set()
    for index, calculation in enumerate(review.calculations):
        try:
            expected = calculate(calculation.expression)
            if calculation.decimal_places is not None:
                with localcontext() as context:
                    context.prec = 50
                    expected = expected.quantize(Decimal(1).scaleb(-calculation.decimal_places),
                                                 rounding=ROUND_HALF_UP)
            stated = Decimal(calculation.result.replace(",", ""))
            valid = stated.is_finite() and expected == stated and stated in numbers
            reviewed.add((expected, re.sub(r"\s+", "", calculation.expression)))
        except (ValueError, DecimalException):
            valid = False
        check(f"calculation_{index}", valid,
              "Safe decimal arithmetic (ROUND_HALF_UP when precision is specified) must equal the stated result, which must appear in the artifact.")
    normalized = without_citations.replace("×", "*").replace("÷", "/")
    normalized = re.sub(r"\b\d{1,3}(?:,\d{3})+(?:\.\d+)?\b", lambda match: match[0].replace(",", ""), normalized)
    for index, (expression, result) in enumerate(EQUATION.findall(normalized)):
        try:
            valid = (Decimal(result), re.sub(r"\s+", "", expression)) in reviewed
        except (ValueError, DecimalException):
            valid = False
        check(f"equation_{index}", valid,
              "Explicit arithmetic in the report must be correct and included in the independent review.")
    passed = all(item["passed"] for item in checks)
    return {"passed": passed, "checks": checks,
            "label": "draft_prepared" if passed else "needs_revision"}
