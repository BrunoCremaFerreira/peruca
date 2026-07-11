"""
Domain service for symbolic math requests (integrate/diff/gradient/limit/
simplify). The LLM only transcribes the expression; this service validates the
request — the expression string is hostile input — and delegates the actual
math to the SymbolicMathEngine port. No CAS library is imported here.
"""

import re

from domain.exceptions import ValidationError
from domain.interfaces.symbolic_math_engine import SymbolicMathEngine

_ALLOWED_OPERATIONS = {"integrate", "diff", "gradient", "limit", "simplify"}
_ALLOWED_FUNCTIONS = {
    "sin", "cos", "tan", "asin", "acos", "atan",
    "sinh", "cosh", "tanh", "exp", "log", "ln", "sqrt", "Abs",
}
_ALLOWED_CONSTANTS = {"pi", "E"}

_MAX_SYMBOLIC_EXPRESSION_LENGTH = 200
_MAX_SYMBOLIC_SYMBOLS = 5
_MAX_SYMBOL_NAME_LENGTH = 8

_ALLOWED_CHARSET_PATTERN = re.compile(r"^[0-9a-zA-Z_+\-*/(). ,^]+$")
_FORBIDDEN_SUBSTRINGS = ("__", "[", "]", '"', "'", "\\", "=", "!", "lambda")
_IDENTIFIER_PATTERN = re.compile(r"([A-Za-z_][A-Za-z0-9_]*)\s*(\(?)")
# A dot is only valid as a decimal separator (digit on both sides); anything
# else is a potential attribute access and is rejected.
_INVALID_DOT_PATTERN = re.compile(r"(?<!\d)\.|\.(?!\d)")
_LIMIT_TARGET_PATTERN = re.compile(r"^-?oo$|^-?\d+(?:\.\d+)?$")


class SymbolicMathService:

    def __init__(self, engine: SymbolicMathEngine):
        self._engine = engine

    def evaluate(
        self,
        operation: str = "",
        expression: str = "",
        variable: str = "",
        to: str = "",
    ) -> str | list[str]:
        operation_name = (operation or "").strip()
        if operation_name not in _ALLOWED_OPERATIONS:
            raise ValidationError(errors=[f"unknown operation: {operation_name}"])

        normalized = self._validate_expression(expression)
        variables = self._parse_variables(variable)

        if operation_name == "integrate":
            return self._engine.integrate(normalized, self._first(variables))
        if operation_name == "diff":
            return self._engine.diff(normalized, self._first(variables))
        if operation_name == "gradient":
            return self._engine.gradient(normalized, variables)
        if operation_name == "limit":
            target = self._validate_limit_target(to)
            return self._engine.limit(normalized, self._first(variables), target)
        return self._engine.simplify(normalized)

    # ===============================================
    # Lexical pre-validation — runs BEFORE any engine
    # ===============================================
    def _validate_expression(self, expression: str) -> str:
        if not isinstance(expression, str) or not expression.strip():
            raise ValidationError(errors=["expression is empty"])
        if len(expression) > _MAX_SYMBOLIC_EXPRESSION_LENGTH:
            raise ValidationError(
                errors=[
                    "expression exceeds the "
                    f"{_MAX_SYMBOLIC_EXPRESSION_LENGTH}-character limit"
                ]
            )
        for forbidden in _FORBIDDEN_SUBSTRINGS:
            if forbidden in expression:
                raise ValidationError(errors=["expression contains forbidden text"])
        if not _ALLOWED_CHARSET_PATTERN.match(expression):
            raise ValidationError(errors=["expression has invalid characters"])
        if _INVALID_DOT_PATTERN.search(expression):
            raise ValidationError(errors=["invalid use of '.' in expression"])
        self._validate_identifiers(expression)
        # `^` never means XOR here: normalize it to the canonical power operator
        # so the engine cannot misread it.
        return expression.replace("^", "**").strip()

    def _validate_identifiers(self, expression: str) -> None:
        free_symbols: set[str] = set()
        for name, opening_paren in _IDENTIFIER_PATTERN.findall(expression):
            if opening_paren:
                if name not in _ALLOWED_FUNCTIONS:
                    raise ValidationError(
                        errors=[f"function not allowed: {name}"]
                    )
                continue
            if name in _ALLOWED_CONSTANTS:
                continue
            if not name.isalpha() or len(name) > _MAX_SYMBOL_NAME_LENGTH:
                raise ValidationError(errors=[f"identifier not allowed: {name}"])
            free_symbols.add(name)
        if len(free_symbols) > _MAX_SYMBOLIC_SYMBOLS:
            raise ValidationError(
                errors=[
                    f"expression exceeds the {_MAX_SYMBOLIC_SYMBOLS}-symbol limit"
                ]
            )

    def _parse_variables(self, variable: str) -> list[str]:
        raw = (variable or "").strip()
        if not raw:
            return []
        names = [piece.strip() for piece in raw.split(",")]
        for name in names:
            if (
                not name
                or not name.isalpha()
                or len(name) > _MAX_SYMBOL_NAME_LENGTH
            ):
                raise ValidationError(errors=[f"invalid variable name: {name}"])
        return names

    @staticmethod
    def _validate_limit_target(to: str) -> str:
        target = (to or "").strip()
        if not _LIMIT_TARGET_PATTERN.match(target):
            raise ValidationError(errors=[f"invalid limit target: {target}"])
        return target

    @staticmethod
    def _first(variables: list[str]) -> str:
        return variables[0] if variables else ""
