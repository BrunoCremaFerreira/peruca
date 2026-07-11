"""
SymPy adapter for the SymbolicMathEngine port.

Security model (the expression string originates from an LLM — hostile):
- sympify()/eval() are NEVER called on the raw string. Parsing goes through
  parse_expr with a whitelisted local_dict, an empty global_dict and
  evaluate=False, followed by a node-walk validation (node count, literal
  exponents) BEFORE any evaluation happens.
- The actual computation runs in a separate long-lived lazy worker process
  with a hard timeout (Process + join-style queue timeout + terminate), since
  integrals may simply never finish.
- SymPy is imported lazily on first use (module-level cache) so startup,
  non-math requests and the unit-test collection never pay its import cost.
"""

import multiprocessing
import queue as queue_module
from functools import partial

from domain.exceptions import (
    CalculationTimeoutError,
    MathDomainError,
    NoClosedFormError,
    ValidationError,
)
from domain.interfaces.symbolic_math_engine import SymbolicMathEngine

_MAX_SYMBOLIC_AST_NODES = 100
_MAX_SYMBOLIC_EXPONENT = 100
_DEFAULT_TIMEOUT_SECONDS = 5.0

_sympy_module = None


def _sympy():
    global _sympy_module
    if _sympy_module is None:
        import sympy

        _sympy_module = sympy
    return _sympy_module


def _parse_local_dict() -> dict:
    sympy = _sympy()
    return {
        # Whitelisted functions and constants.
        "sin": sympy.sin,
        "cos": sympy.cos,
        "tan": sympy.tan,
        "asin": sympy.asin,
        "acos": sympy.acos,
        "atan": sympy.atan,
        "sinh": sympy.sinh,
        "cosh": sympy.cosh,
        "tanh": sympy.tanh,
        "exp": sympy.exp,
        "log": sympy.log,
        "ln": sympy.log,
        "sqrt": sympy.sqrt,
        "Abs": sympy.Abs,
        "pi": sympy.pi,
        "E": sympy.E,
        # Constructors the parser transformations emit.
        "Symbol": sympy.Symbol,
        "Integer": sympy.Integer,
        "Float": sympy.Float,
        "Rational": sympy.Rational,
        "Add": sympy.Add,
        "Mul": sympy.Mul,
        "Pow": sympy.Pow,
    }


def _safe_parse(expression: str):
    """
    Parse with the restricted namespace and validate the unevaluated tree
    (node count, literal exponents) before returning the evaluated form.
    """
    sympy = _sympy()
    from sympy.parsing.sympy_parser import parse_expr, standard_transformations

    local_dict = _parse_local_dict()
    try:
        unevaluated = parse_expr(
            expression,
            local_dict=local_dict,
            global_dict={},
            evaluate=False,
            transformations=standard_transformations,
        )
    except Exception as error:  # noqa: BLE001 - parser raises many types
        raise ValidationError(errors=[f"cannot parse expression: {error}"]) from error
    if not isinstance(unevaluated, sympy.Basic):
        raise ValidationError(errors=["expression is not a mathematical object"])

    node_count = _validate_tree(unevaluated)
    if node_count > _MAX_SYMBOLIC_AST_NODES:
        raise ValidationError(
            errors=[f"expression exceeds the {_MAX_SYMBOLIC_AST_NODES}-node limit"]
        )

    # The tree is proven safe (bounded exponents/size): evaluating is now
    # harmless and gives SymPy its canonical arithmetic (e.g. log(0) -> zoo).
    try:
        return parse_expr(
            expression,
            local_dict=local_dict,
            global_dict={},
            evaluate=True,
            transformations=standard_transformations,
        )
    except Exception as error:  # noqa: BLE001
        raise ValidationError(errors=[f"cannot evaluate expression: {error}"]) from error


def _validate_tree(node) -> int:
    """
    Post-order walk: children first, so an inner Pow with a huge literal
    exponent is rejected before any outer numeric exponent gets bounded.
    Returns the total node count.
    """
    sympy = _sympy()
    count = 1
    for argument in node.args:
        count += _validate_tree(argument)
    if isinstance(node, sympy.Pow):
        _validate_exponent(node.exp)
    return count


def _validate_exponent(exponent) -> None:
    sympy = _sympy()
    if exponent.free_symbols:
        return
    if isinstance(exponent, sympy.Number):
        if abs(exponent) > _MAX_SYMBOLIC_EXPONENT:
            raise ValidationError(
                errors=[f"exponent exceeds the {_MAX_SYMBOLIC_EXPONENT} limit"]
            )
        return
    try:
        magnitude = abs(float(exponent))
    except (OverflowError, TypeError, ValueError) as error:
        raise ValidationError(errors=["exponent is too large"]) from error
    if magnitude > _MAX_SYMBOLIC_EXPONENT:
        raise ValidationError(
            errors=[f"exponent exceeds the {_MAX_SYMBOLIC_EXPONENT} limit"]
        )


# ===========================================================================
# Worker-side computation (module-level so it is picklable)
# ===========================================================================


def _default_symbol(parsed):
    sympy = _sympy()
    free = sorted(parsed.free_symbols, key=lambda symbol: symbol.name)
    return free[0] if free else sympy.Symbol("x")


def _limit_target(to: str):
    sympy = _sympy()
    if to == "oo":
        return sympy.oo
    if to == "-oo":
        return -sympy.oo
    return sympy.Float(to) if "." in to else sympy.Integer(to)


def _compute(operation: str, expression: str, variables: tuple, to: str):
    sympy = _sympy()
    parsed = _safe_parse(expression)
    symbols = [sympy.Symbol(name) for name in variables]

    if operation == "integrate":
        symbol = symbols[0] if symbols else _default_symbol(parsed)
        return sympy.integrate(parsed, symbol)
    if operation == "diff":
        symbol = symbols[0] if symbols else _default_symbol(parsed)
        return sympy.diff(parsed, symbol)
    if operation == "gradient":
        if symbols:
            ordered = symbols
        else:
            ordered = sorted(parsed.free_symbols, key=lambda symbol: symbol.name)
        return [sympy.diff(parsed, symbol) for symbol in ordered]
    if operation == "limit":
        symbol = symbols[0] if symbols else _default_symbol(parsed)
        return sympy.limit(parsed, symbol, _limit_target(to))
    return sympy.simplify(parsed)


def _worker_loop(request_queue, response_queue) -> None:
    while True:
        fn = request_queue.get()
        try:
            response_queue.put((True, fn()))
        except Exception as error:  # noqa: BLE001 - transported to the parent
            response_queue.put((False, error))


# ===========================================================================
# Adapter
# ===========================================================================


class SympySymbolicMathEngine(SymbolicMathEngine):

    def __init__(self, timeout_seconds: float = _DEFAULT_TIMEOUT_SECONDS):
        self._timeout_seconds = timeout_seconds
        self._worker = None
        self._request_queue = None
        self._response_queue = None

    # -------------------------------------------------
    # Port implementation
    # -------------------------------------------------
    def integrate(self, expression: str, variable: str) -> str:
        result = self._evaluate("integrate", expression, (variable,), "")
        if result.has(_sympy().Integral):
            raise NoClosedFormError(
                errors=["integral has no closed-form solution"]
            )
        return self._stringify(self._post_check(result))

    def diff(self, expression: str, variable: str) -> str:
        result = self._evaluate("diff", expression, (variable,), "")
        return self._stringify(self._post_check(result))

    def gradient(self, expression: str, variables: list[str]) -> list[str]:
        results = self._evaluate("gradient", expression, tuple(variables), "")
        return [self._stringify(self._post_check(result)) for result in results]

    def limit(self, expression: str, variable: str, to: str) -> str:
        sympy = _sympy()
        result = self._evaluate("limit", expression, (variable,), to)
        result = self._post_check(result)
        if result in (sympy.oo, -sympy.oo) or bool(result.is_infinite):
            raise MathDomainError(errors=["limit diverges"])
        return self._stringify(result)

    def simplify(self, expression: str) -> str:
        result = self._evaluate("simplify", expression, (), "")
        return self._stringify(self._post_check(result))

    # -------------------------------------------------
    # Execution with process isolation + timeout
    # -------------------------------------------------
    def _evaluate(self, operation: str, expression: str, variables: tuple, to: str):
        variables = tuple(name for name in variables if name)
        # Validate in the parent first: hostile strings are rejected fast and
        # deterministically, without ever reaching the worker.
        _safe_parse(expression)
        return self._run_with_timeout(
            partial(_compute, operation, expression, variables, to)
        )

    def _run_with_timeout(self, fn):
        self._ensure_worker()
        self._request_queue.put(fn)
        try:
            success, payload = self._response_queue.get(
                timeout=self._timeout_seconds
            )
        except queue_module.Empty:
            self._terminate_worker()
            raise CalculationTimeoutError(
                errors=["symbolic calculation timed out"]
            ) from None
        if success:
            return payload
        if isinstance(payload, ValidationError):
            raise payload
        raise ValidationError(
            errors=[f"symbolic engine failed: {payload}"]
        ) from payload

    def _ensure_worker(self) -> None:
        if self._worker is not None and self._worker.is_alive():
            return
        context = multiprocessing.get_context()
        self._request_queue = context.Queue()
        self._response_queue = context.Queue()
        self._worker = context.Process(
            target=_worker_loop,
            args=(self._request_queue, self._response_queue),
            daemon=True,
        )
        self._worker.start()

    def _terminate_worker(self) -> None:
        if self._worker is not None:
            self._worker.terminate()
            self._worker.join(timeout=1.0)
        for pending_queue in (self._request_queue, self._response_queue):
            if pending_queue is not None:
                pending_queue.close()
                pending_queue.cancel_join_thread()
        self._worker = None
        self._request_queue = None
        self._response_queue = None

    # -------------------------------------------------
    # Result post-checks
    # -------------------------------------------------
    def _post_check(self, result):
        sympy = _sympy()
        result = self._surface_generic_branch(result)
        if result.has(sympy.zoo, sympy.nan):
            raise MathDomainError(errors=["result is undefined (zoo/nan)"])
        return result

    @staticmethod
    def _surface_generic_branch(result):
        # Parametric results come back as Piecewise; the user expects the
        # generic branch, never the Piecewise object itself. Depending on the
        # SymPy version the generic branch is either guarded by Ne(param, 0)
        # (with the degenerate case as the True fallback) or is itself the
        # True fallback — prefer the Ne branch, then the True one.
        sympy = _sympy()
        for piecewise in result.atoms(sympy.Piecewise):
            generic = None
            for branch_expression, condition in piecewise.args:
                if isinstance(condition, sympy.Ne):
                    generic = branch_expression
                    break
            if generic is None:
                for branch_expression, condition in piecewise.args:
                    if condition == sympy.true:
                        generic = branch_expression
                        break
            if generic is None:
                generic = piecewise.args[-1].expr
            result = result.xreplace({piecewise: generic})
        return result

    @staticmethod
    def _stringify(result) -> str:
        return str(result)
