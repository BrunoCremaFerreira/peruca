"""
calculator_service unit tests (TDD RED — written before implementation).

The LLM never does math (golden rule, plan §1): it only transcribes the
dictated expression into a canonical string; this module evaluates it
deterministically with Decimal, folding LEFT TO RIGHT with NO operator
precedence (plan §3 / §4.2). Grammar: `+ - * / **`, `%`-suffixed operands and
the numeric-literal functions sqrt / ln / log10 / log(x, base). The input
comes from the LLM, so it is treated as hostile: closed-set tokenizer, hard
caps, never eval()/ast.literal_eval().

API under test (src/domain/services/calculator_service.py, to be created):
    evaluate_expression(expression: str) -> Decimal

Expected exceptions (domain/exceptions.py):
    ValidationError (already exists)
    DivisionByZeroError(ValidationError)  (new)
    MathDomainError(ValidationError)      (new)

Product symbols are resolved lazily inside fixtures so this file COLLECTS
before the implementation exists; every test then fails RED at setup/runtime.
"""

import time
from decimal import Decimal

import pytest

from domain.exceptions import ValidationError


@pytest.fixture
def evaluate():
    from domain.services.calculator_service import evaluate_expression

    return evaluate_expression


@pytest.fixture
def exceptions():
    import domain.exceptions as domain_exceptions

    return domain_exceptions


# ===========================================================================
# Round 1 batteries (plan §9.1)
# ===========================================================================


class TestEvaluateBasicOperations:
    def test_addition__returns_sum(self, evaluate):
        assert evaluate("2 + 3") == Decimal("5")

    def test_subtraction__returns_difference(self, evaluate):
        assert evaluate("10 - 4") == Decimal("6")

    def test_multiplication__returns_product(self, evaluate):
        assert evaluate("6 * 7") == Decimal("42")

    def test_division__returns_exact_decimal(self, evaluate):
        assert evaluate("10 / 4") == Decimal("2.5")


class TestEvaluateSequentialOrder:
    """Central business rule: left-to-right fold, NO operator precedence."""

    def test_two_plus_three_times_four__is_twenty_not_fourteen(self, evaluate):
        # This test documents the decision: spoken order wins, never PEMDAS.
        assert evaluate("2 + 3 * 4") == Decimal("20")

    def test_ten_div_two_plus_three__is_eight(self, evaluate):
        assert evaluate("10 / 2 + 3") == Decimal("8")

    def test_five_minus_one_times_three__is_twelve(self, evaluate):
        assert evaluate("5 - 1 * 3") == Decimal("12")

    def test_chain_with_five_operands__folds_left_to_right(self, evaluate):
        # ((((1 + 2) * 3) - 4) / 5) = 1
        assert evaluate("1 + 2 * 3 - 4 / 5") == Decimal("1")


class TestEvaluateDecimalPrecision:
    def test_point_one_plus_point_two__is_exactly_point_three(self, evaluate):
        assert evaluate("0.1 + 0.2") == Decimal("0.3")

    def test_one_third__quantization_follows_default_decimal_context(self, evaluate):
        # The domain returns the raw Decimal computed under the default
        # 28-digit context (plan §4.4); presentation rounding is graph work.
        assert evaluate("1 / 3") == Decimal(1) / Decimal(3)

    def test_one_point_five_minus_two_point_seven__is_exact(self, evaluate):
        assert evaluate("1.5 - 2.7") == Decimal("-1.2")


class TestEvaluateNegativesAndEdges:
    def test_negative_first_operand__computes(self, evaluate):
        assert evaluate("-5 + 3") == Decimal("-2")

    def test_result_zero__returns_zero(self, evaluate):
        assert evaluate("5 - 5") == Decimal("0")

    def test_single_value__identity(self, evaluate):
        assert evaluate("42") == Decimal("42")

    def test_single_negative_decimal__identity(self, evaluate):
        assert evaluate("-7.5") == Decimal("-7.5")

    def test_zero_divided_by_value__returns_zero(self, evaluate):
        assert evaluate("0 / 5") == Decimal("0")


class TestEvaluateDivisionByZero:
    def test_division_by_zero__raises_division_by_zero_error(
        self, evaluate, exceptions
    ):
        with pytest.raises(exceptions.DivisionByZeroError):
            evaluate("10 / 0")

    def test_division_by_zero_mid_chain__aborts_whole_chain(
        self, evaluate, exceptions
    ):
        with pytest.raises(exceptions.DivisionByZeroError):
            evaluate("4 + 6 / 0 - 1")

    def test_division_by_zero_error__is_a_validation_error(self, exceptions):
        # The route layer already maps ValidationError; the subclass must
        # inherit it so no new HTTP mapping is needed.
        assert issubclass(exceptions.DivisionByZeroError, ValidationError)


class TestEvaluateMalformedInput:
    def test_empty_string__raises_validation_error(self, evaluate):
        with pytest.raises(ValidationError):
            evaluate("")

    def test_whitespace_only__raises_validation_error(self, evaluate):
        with pytest.raises(ValidationError):
            evaluate("   ")

    def test_trailing_operator__raises_validation_error(self, evaluate):
        with pytest.raises(ValidationError):
            evaluate("5 +")

    def test_caret_operator__raises_validation_error(self, evaluate):
        # `^` is not canonical syntax — power is `**` (plan §9.1).
        with pytest.raises(ValidationError):
            evaluate("2 ^ 3")

    def test_plain_text__raises_validation_error(self, evaluate):
        with pytest.raises(ValidationError):
            evaluate("dez mais cinco")

    def test_scientific_notation__raises_validation_error(self, evaluate):
        # DoS hardening: `1E+999` must be rejected by construction, never
        # turned into a giant Decimal (plan §4.2).
        with pytest.raises(ValidationError):
            evaluate("1E+999")

    def test_nan_literal__raises_validation_error(self, evaluate):
        with pytest.raises(ValidationError):
            evaluate("NaN")

    def test_infinity_literal__raises_validation_error(self, evaluate):
        with pytest.raises(ValidationError):
            evaluate("Infinity")

    def test_none_input__raises_validation_error(self, evaluate):
        with pytest.raises(ValidationError):
            evaluate(None)

    def test_non_string_input__raises_validation_error(self, evaluate):
        with pytest.raises(ValidationError):
            evaluate(123)


class TestEvaluateLimits:
    def test_more_than_fifty_operands__raises_validation_error(self, evaluate):
        expression = " + ".join(["1"] * 51)
        with pytest.raises(ValidationError):
            evaluate(expression)

    def test_exactly_fifty_operands__accepted(self, evaluate):
        expression = " + ".join(["1"] * 50)
        assert evaluate(expression) == Decimal("50")

    def test_value_longer_than_twenty_digits__raises_validation_error(self, evaluate):
        with pytest.raises(ValidationError):
            evaluate(("9" * 21) + " + 1")

    def test_value_with_exactly_twenty_digits__accepted(self, evaluate):
        twenty_nines = "9" * 20
        assert evaluate(f"{twenty_nines} - {twenty_nines}") == Decimal("0")


# ===========================================================================
# Round 2 batteries — scientific extension (plan §9.1, 2026-07-10)
# ===========================================================================


class TestEvaluateSquareRoot:
    def test_sqrt_perfect_square__returns_exact(self, evaluate):
        assert evaluate("sqrt(144)") == Decimal("12")

    def test_sqrt_irrational__quantization_fixed(self, evaluate):
        # Fixed to Decimal's own sqrt under the default context (plan §4.1).
        assert evaluate("sqrt(2)") == Decimal(2).sqrt()

    def test_sqrt_zero__returns_zero(self, evaluate):
        assert evaluate("sqrt(0)") == Decimal("0")

    def test_sqrt_negative__raises_math_domain_error(self, evaluate, exceptions):
        # Never leak decimal.InvalidOperation (plan §4.2).
        with pytest.raises(exceptions.MathDomainError):
            evaluate("sqrt(-4)")


class TestEvaluateLogarithm:
    def test_log10_power_of_ten__returns_exact_integer(self, evaluate):
        assert evaluate("log10(1000)") == Decimal("3")

    def test_ln_of_one__returns_zero(self, evaluate):
        assert evaluate("ln(1)") == Decimal("0")

    def test_log_base_n__computed_as_ln_ratio(self, evaluate):
        # log(x, base) = ln(x) / ln(base) — the formula itself is the fixed
        # contract (plan §4.1), so the expected value is computed the same way.
        assert evaluate("log(8, 2)") == Decimal(8).ln() / Decimal(2).ln()

    def test_log_of_zero__raises_math_domain_error(self, evaluate, exceptions):
        with pytest.raises(exceptions.MathDomainError):
            evaluate("log10(0)")

    def test_log_of_negative__raises_math_domain_error(self, evaluate, exceptions):
        with pytest.raises(exceptions.MathDomainError):
            evaluate("ln(-5)")

    def test_log_base_one__raises_validation_error(self, evaluate):
        # MathDomainError subclasses ValidationError, so this assertion holds
        # whichever of the two the implementation picks (plan §4.2 vs §9.1).
        with pytest.raises(ValidationError):
            evaluate("log(8, 1)")

    def test_log_base_zero_or_negative__raises_validation_error(self, evaluate):
        with pytest.raises(ValidationError):
            evaluate("log(8, 0)")
        with pytest.raises(ValidationError):
            evaluate("log(8, -2)")


class TestEvaluatePercentage:
    """
    Desk-calculator percent semantics resolved in the fold (plan §4.2):
    with + / - the `n%` operand is relative to the accumulator; with * / /
    it is the plain factor n/100. The LLM never converts anything.
    """

    def test_percent_of__x_percent_de_y__returns_fraction(self, evaluate):
        # "10% de 200" is transcribed as "10% * 200".
        assert evaluate("10% * 200") == Decimal("20")

    def test_percent_increase__y_mais_x_percent__returns_increased(self, evaluate):
        assert evaluate("150 + 10%") == Decimal("165")

    def test_percent_decrease__y_menos_x_percent__returns_decreased(self, evaluate):
        assert evaluate("200 - 25%") == Decimal("150")

    def test_percent_of_decimal_value__exact_decimal(self, evaluate):
        # No float anywhere in the path: 10% of 0.3 is exactly 0.03.
        assert evaluate("10% * 0.3") == Decimal("0.03")

    def test_percent_chained_in_sequence__folds_left_to_right(self, evaluate):
        # Interaction with the sequential rule: 100 +10% = 110, then +10% of
        # the ACCUMULATOR = 121 (not 120).
        assert evaluate("100 + 10% + 10%") == Decimal("121")

    def test_percent_negative_base__computes(self, evaluate):
        # Policy fixed by this test: the multiplicative rule applies to a
        # negative accumulator too: -100 * (1 + 10/100) = -110.
        assert evaluate("-100 + 10%") == Decimal("-110")


class TestEvaluatePower:
    def test_power_integer_exponent__exact(self, evaluate):
        assert evaluate("2 ** 10") == Decimal("1024")

    def test_power_negative_exponent__returns_fraction(self, evaluate):
        assert evaluate("2 ** -1") == Decimal("0.5")

    def test_power_fractional_exponent__quantization_fixed(self, evaluate):
        # Fixed to Decimal's own power under the default context.
        assert evaluate("2 ** 0.5") == Decimal(2) ** Decimal("0.5")

    def test_power_zero_to_zero__policy_fixed(self, evaluate, exceptions):
        # Decision documented by this test: 0 ** 0 is mathematically
        # indeterminate -> MathDomainError (never a leaked
        # decimal.InvalidOperation, never the silent convention "= 1").
        with pytest.raises(exceptions.MathDomainError):
            evaluate("0 ** 0")

    def test_power_exponent_exceeds_cap__raises_validation_error_fast(self, evaluate):
        # |exponent| <= 100 is a PRE-CHECK (plan §4.2): the rejection must be
        # immediate, never "compute and see if it blows up".
        started = time.monotonic()
        with pytest.raises(ValidationError):
            evaluate("2 ** 101")
        with pytest.raises(ValidationError):
            evaluate("9 ** 999999999")
        assert time.monotonic() - started < 1.0

    def test_power_in_sequential_chain__no_precedence(self, evaluate):
        # Extends the order-documenting test: (2 + 3) ** 2 = 25, not 11.
        assert evaluate("2 + 3 ** 2") == Decimal("25")


class TestEvaluateExtendedGrammar:
    """The closed-set tokenizer replaced the single regex — re-fix hardening."""

    def test_function_syntax_accepted__sqrt_log(self, evaluate):
        assert evaluate("sqrt(144) + 6") == Decimal("18")
        assert evaluate("log(100, 10) * 3") == Decimal("6")

    def test_scientific_notation_still_rejected__validation_error(self, evaluate):
        # Regression guard for the tokenizer rewrite.
        with pytest.raises(ValidationError):
            evaluate("2e10 + 1")
        with pytest.raises(ValidationError):
            evaluate("1E+999")

    def test_unknown_function_name__raises_validation_error(self, evaluate):
        with pytest.raises(ValidationError):
            evaluate("foo(3)")

    def test_nested_function_or_symbolic_arg__raises_validation_error(self, evaluate):
        # Non-literal arguments belong to the symbolic path (plan §4.1);
        # the numeric grammar only accepts numeric literals inside calls.
        with pytest.raises(ValidationError):
            evaluate("sqrt(sqrt(16))")
        with pytest.raises(ValidationError):
            evaluate("sqrt(x)")
