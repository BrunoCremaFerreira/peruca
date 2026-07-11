"""
symbolic_math_service unit tests (TDD RED — written before implementation).

The LLM only transcribes ("x**3" + operation "diff"); all symbolic math runs
in Python behind a domain port (plan §4.1/§4.3):

    domain/interfaces/symbolic_math_engine.py  -> ABC SymbolicMathEngine
    domain/services/symbolic_math_service.py   -> SymbolicMathService(engine)
    infra/math/sympy_symbolic_math_engine.py   -> SympySymbolicMathEngine

Contract fixed by these tests:
    SymbolicMathService(engine).evaluate(
        operation: str,   # closed set: integrate|diff|gradient|limit|simplify
        expression: str,
        variable: str = "",   # flat string, "x" or "x,y,z"
        to: str = "",         # limit target only ("0", "oo")
    ) -> str | list[str]      # canonical expression string(s); gradient -> list

    SympySymbolicMathEngine(timeout_seconds: float = 5.0)
        ._run_with_timeout(fn) -> result of fn() or CalculationTimeoutError

Expected exceptions (domain/exceptions.py, all ValidationError subclasses):
    NoClosedFormError, CalculationTimeoutError, MathDomainError.

Symbolic equality rule (plan §9.1b): NEVER compare full strings. Integrals are
verified by the derivative round-trip; everything else by simplify(a - b) == 0
with an .equals() numeric-sampling fallback. The LLM-originated string is
hostile: security tests assert rejection BEFORE the engine is touched.

Product symbols are imported lazily inside helpers so this file COLLECTS
before the implementation exists; every test then fails RED at runtime.
"""

import time
from unittest.mock import MagicMock

import pytest
import sympy

from domain.exceptions import ValidationError


# ===========================================================================
# Lazy product accessors (implementation does not exist yet)
# ===========================================================================


def _exceptions():
    import domain.exceptions as domain_exceptions

    return domain_exceptions


def _service(engine):
    from domain.services.symbolic_math_service import SymbolicMathService

    return SymbolicMathService(engine)


def _real_engine(timeout_seconds=None):
    from infra.math.sympy_symbolic_math_engine import SympySymbolicMathEngine

    if timeout_seconds is None:
        return SympySymbolicMathEngine()
    return SympySymbolicMathEngine(timeout_seconds=timeout_seconds)


def _real_service():
    return _service(_real_engine())


# ===========================================================================
# Symbolic-equality helpers (test-side; input strings here are trusted)
# ===========================================================================


def _assert_symbolic_equal(actual_str: str, expected_str: str):
    actual = sympy.sympify(actual_str)
    expected = sympy.sympify(expected_str)
    difference = sympy.simplify(actual - expected)
    if difference != 0:
        # simplify() returning non-zero does not prove inequality — fall back
        # to numeric sampling before failing (plan §9.1b).
        assert actual.equals(expected), f"{actual!r} != {expected!r}"


def _assert_antiderivative_of(result_str: str, integrand_str: str, variable: str):
    # Primary assert for integrals: derivative round-trip validates the
    # antiderivative up to a constant, independent of the form the installed
    # SymPy version chose (plan §9.1b).
    symbol = sympy.Symbol(variable)
    result = sympy.sympify(result_str)
    integrand = sympy.sympify(integrand_str)
    difference = sympy.simplify(sympy.diff(result, symbol) - integrand)
    if difference != 0:
        assert sympy.diff(result, symbol).equals(integrand), (
            f"d/d{variable}({result!r}) != {integrand!r}"
        )


# Module-level so they are picklable by a multiprocessing-based timeout seam.
def _slow_fn():
    time.sleep(0.3)
    return "late"


def _fast_fn():
    return "ok"


# ===========================================================================
# Math batteries — real SymPy engine behind the domain service
# ===========================================================================


class TestIntegrate:
    def test_integrate_cos_squared__antiderivative_verified_by_derivative(self):
        service = _real_service()
        result = service.evaluate(
            operation="integrate", expression="cos(w*x)**2", variable="x"
        )
        # Parametric integral: SymPy returns a Piecewise; the service must
        # surface the generic branch (condition True), never the Piecewise
        # object itself (plan §4.3).
        assert "Piecewise" not in result
        assert not sympy.sympify(result).has(sympy.Piecewise)
        _assert_antiderivative_of(result, "cos(w*x)**2", "x")

    def test_integrate_polynomial__exact_form(self):
        service = _real_service()
        result = service.evaluate(
            operation="integrate", expression="x**2", variable="x"
        )
        _assert_symbolic_equal(result, "x**3/3")

    def test_integrate_no_closed_form__raises_no_closed_form_error(self):
        # SymPy returns an unevaluated Integral (no exception) for x**x; the
        # post-check must detect it and map it (plan §4.3).
        service = _real_service()
        with pytest.raises(_exceptions().NoClosedFormError):
            service.evaluate(operation="integrate", expression="x**x", variable="x")

    def test_integrate_result_is_zoo_or_nan__raises_math_domain_error(self):
        # log(0) evaluates to zoo, not an exception: without the has(zoo, nan)
        # post-check the user would read "zoo" in the chat (plan §4.3).
        service = _real_service()
        with pytest.raises(_exceptions().MathDomainError):
            service.evaluate(
                operation="integrate", expression="log(0)", variable="x"
            )


class TestDifferentiate:
    def test_derivative_polynomial_plus_trig__symbolic_equality(self):
        service = _real_service()
        result = service.evaluate(
            operation="diff", expression="x**3 + sin(x)", variable="x"
        )
        _assert_symbolic_equal(result, "3*x**2 + cos(x)")

    def test_derivative_with_respect_to_named_symbol__uses_declared_variable(self):
        service = _real_service()
        result = service.evaluate(
            operation="diff", expression="x*y**2", variable="y"
        )
        _assert_symbolic_equal(result, "2*x*y")


class TestGradient:
    def test_gradient_two_variables__returns_ordered_vector(self):
        # Vector order follows the declared variable order — without it the
        # output flakes between runs (plan §4.3).
        service = _real_service()
        result = service.evaluate(
            operation="gradient", expression="x**2*y", variable="x,y"
        )
        assert isinstance(result, list)
        assert len(result) == 2
        _assert_symbolic_equal(result[0], "2*x*y")
        _assert_symbolic_equal(result[1], "x**2")

    def test_gradient_single_variable__degenerate_returns_derivative(self):
        service = _real_service()
        result = service.evaluate(
            operation="gradient", expression="x**2", variable="x"
        )
        assert isinstance(result, list)
        assert len(result) == 1
        _assert_symbolic_equal(result[0], "2*x")


class TestLimit:
    def test_limit_sin_x_over_x_at_zero__returns_one(self):
        service = _real_service()
        result = service.evaluate(
            operation="limit", expression="sin(x)/x", variable="x", to="0"
        )
        assert sympy.sympify(result) == 1

    def test_limit_divergent__returns_infinity_mapped_to_friendly_error(self):
        # Decision documented by this test: a divergent limit (oo/-oo/zoo)
        # raises MathDomainError; the raw "oo" string never reaches the chat.
        service = _real_service()
        with pytest.raises(_exceptions().MathDomainError):
            service.evaluate(
                operation="limit", expression="1/x**2", variable="x", to="0"
            )


class TestSimplify:
    def test_simplify_trig_identity__reduces(self):
        service = _real_service()
        result = service.evaluate(
            operation="simplify", expression="sin(x)**2 + cos(x)**2"
        )
        assert sympy.sympify(result) == 1


class TestOperationValidation:
    def test_unknown_operation__raises_validation_error_and_never_hits_engine(self):
        # The closed operation set is validated in the domain service (§4.1).
        engine = MagicMock()
        service = _service(engine)
        with pytest.raises(ValidationError):
            service.evaluate(operation="algebra", expression="x + x", variable="x")
        assert engine.method_calls == []


# ===========================================================================
# Timeout — injectable seam, never the production 5 s (plan §9.1b)
# ===========================================================================


class TestTimeout:
    def test_run_with_timeout__slow_fn__raises_calculation_timeout_error(self):
        engine = _real_engine(timeout_seconds=0.05)
        with pytest.raises(_exceptions().CalculationTimeoutError):
            engine._run_with_timeout(_slow_fn)

    def test_run_with_timeout__fast_fn__returns_result(self):
        engine = _real_engine(timeout_seconds=2.0)
        assert engine._run_with_timeout(_fast_fn) == "ok"

    def test_evaluate__internal_timeout_raised__maps_to_friendly_error(self):
        # When the engine's worker times out, the service must surface the
        # domain CalculationTimeoutError (a ValidationError — friendly and
        # already handled by the graph), never a raw TimeoutError.
        exceptions = _exceptions()
        engine = MagicMock()
        engine.integrate.side_effect = exceptions.CalculationTimeoutError(
            errors=["calculation timed out"]
        )
        service = _service(engine)
        with pytest.raises(exceptions.CalculationTimeoutError) as exc_info:
            service.evaluate(
                operation="integrate", expression="cos(w*x)**2", variable="x"
            )
        assert isinstance(exc_info.value, ValidationError)


# ===========================================================================
# Security hardening — the expression string comes from the LLM (hostile)
# ===========================================================================


class TestSecurityHardening:
    """
    Mirrors test_graph_classify_literal_eval_safety.py: sympify() uses eval()
    internally and is forbidden; barriers are lexical pre-validation (service),
    restricted parse_expr(evaluate=False) + node walk (adapter), and hard caps
    (plan §4.3). Pre-lexical rejections must happen BEFORE any engine call.
    """

    def test_dunder_import_string__raises_validation_error(self):
        engine = MagicMock()
        service = _service(engine)
        with pytest.raises(ValidationError):
            service.evaluate(
                operation="simplify", expression="__import__('os').system('ls')"
            )
        assert engine.method_calls == []

    def test_attribute_access_string__raises_validation_error(self):
        engine = MagicMock()
        service = _service(engine)
        for hostile in ["().__class__.__mro__", "x.__class__"]:
            with pytest.raises(ValidationError):
                service.evaluate(operation="simplify", expression=hostile)
        assert engine.method_calls == []

    def test_function_outside_whitelist__raises_validation_error(self):
        engine = MagicMock()
        service = _service(engine)
        for hostile in ["Lambda(x, x)", "factorial(5)"]:
            with pytest.raises(ValidationError):
                service.evaluate(
                    operation="simplify", expression=hostile, variable="x"
                )
        assert engine.method_calls == []

    def test_expression_exceeds_length_cap__raises_validation_error_before_parse(self):
        engine = MagicMock()
        service = _service(engine)
        too_long = "x + " * 60 + "x"  # > 200 chars
        assert len(too_long) > 200
        with pytest.raises(ValidationError):
            service.evaluate(operation="simplify", expression=too_long, variable="x")
        assert engine.method_calls == []

    def test_node_count_exceeds_cap__raises_validation_error(self):
        # Under the 200-char cap but over the 100-node AST cap: 39 Pow terms
        # ~= 118 preorder nodes. Checked post-parse in the adapter.
        service = _real_service()
        expression = "+".join(["x**2"] * 39)
        assert len(expression) <= 200
        with pytest.raises(ValidationError):
            service.evaluate(operation="simplify", expression=expression, variable="x")

    def test_huge_numeric_literal_in_symbolic__raises_validation_error(self):
        # Forces the evaluate=False + walk contract: with evaluate=True,
        # 10**10**10 is computed AT PARSE TIME (plan §4.3).
        service = _real_service()
        started = time.monotonic()
        with pytest.raises(ValidationError):
            service.evaluate(operation="simplify", expression="10**10**10")
        assert time.monotonic() - started < 2.0

    def test_unknown_free_symbols__allowed(self):
        # Documents the distinction: arbitrary free symbols are fine; only
        # CALLS to functions outside the whitelist are rejected (plan §4.3).
        service = _real_service()
        result = service.evaluate(operation="diff", expression="q*t", variable="t")
        _assert_symbolic_equal(result, "q")
