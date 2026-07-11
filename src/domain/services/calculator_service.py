"""
Deterministic evaluator for user-dictated arithmetic expressions.

The LLM never does math: it only transcribes the dictated expression into a
canonical string ("10 + 5 * 2", "sqrt(144)", "150 + 15%"). This module
evaluates that string with Decimal, folding LEFT TO RIGHT with NO operator
precedence — the spoken order wins.

The input string originates from an LLM and is treated as hostile: it is
consumed by a closed-set tokenizer (never eval()/ast.literal_eval()) with hard
caps on operand count, digits per value and exponent magnitude.

Module of pure functions (stdlib only), following the date_resolver precedent.
"""

import re
from decimal import (
    Decimal,
    DivisionByZero as _DecimalDivisionByZero,
    InvalidOperation as _DecimalInvalidOperation,
    Overflow as _DecimalOverflow,
)

from domain.exceptions import DivisionByZeroError, MathDomainError, ValidationError

_MAX_OPERANDS = 50
_MAX_DIGITS_PER_VALUE = 20
_MAX_EXPONENT = Decimal(100)
_MAX_ESTIMATED_RESULT_DIGITS = 10_000

_ONE_HUNDRED = Decimal(100)

_ALLOWED_FUNCTIONS = {"sqrt", "ln", "log10", "log"}

# Closed-set grammar: a function call over literal arguments, an (unsigned)
# numeric literal with an optional percent suffix, or an operator. Anything
# else (scientific notation, NaN/Infinity, `=`, `^`, plain text, nested or
# symbolic function arguments) fails to tokenize by construction.
_TOKEN_PATTERN = re.compile(
    r"(?P<function>[A-Za-z_][A-Za-z0-9_]*)\((?P<arguments>[^()]*)\)"
    r"|(?P<number>\d+(?:\.\d+)?%?)"
    r"|(?P<operator>\*\*|[+\-*/])"
)
_FUNCTION_ARGUMENT_PATTERN = re.compile(r"^-?\d+(?:\.\d+)?$")


def evaluate_expression(expression: str) -> Decimal:
    """
    Evaluate a canonical arithmetic expression left-to-right (no precedence)
    and return the raw Decimal computed under the default context.
    """
    if not isinstance(expression, str):
        raise ValidationError(errors=["expression must be a string"])
    normalized = expression.strip()
    if not normalized:
        raise ValidationError(errors=["expression is empty"])
    # Residual decimal comma ("2,5") is normalized deterministically. Function
    # argument separators are emitted as ", " (comma + space) by the prompt, so
    # only a comma squeezed between two digits is a decimal separator.
    normalized = re.sub(r"(?<=\d),(?=\d)", ".", normalized)

    tokens = _tokenize(normalized)
    operands, operators = _parse(tokens)
    if len(operands) > _MAX_OPERANDS:
        raise ValidationError(
            errors=[f"expression exceeds the {_MAX_OPERANDS}-operand limit"]
        )
    return _fold(operands, operators)


def _tokenize(expression: str) -> list[tuple[str, object]]:
    tokens: list[tuple[str, object]] = []
    position = 0
    length = len(expression)
    while position < length:
        if expression[position].isspace():
            position += 1
            continue
        match = _TOKEN_PATTERN.match(expression, position)
        if match is None:
            raise ValidationError(
                errors=[f"unexpected token at position {position}"]
            )
        if match.group("function") is not None:
            tokens.append(
                ("function", (match.group("function"), match.group("arguments")))
            )
        elif match.group("number") is not None:
            tokens.append(("number", match.group("number")))
        else:
            tokens.append(("operator", match.group("operator")))
        position = match.end()
    return tokens


def _parse(
    tokens: list[tuple[str, object]],
) -> tuple[list[tuple[Decimal, bool]], list[str]]:
    operands: list[tuple[Decimal, bool]] = []
    operators: list[str] = []
    expecting_operand = True
    index = 0
    while index < len(tokens):
        kind, payload = tokens[index]
        if expecting_operand:
            if kind == "operator" and payload == "-":
                if index + 1 < len(tokens) and tokens[index + 1][0] == "number":
                    operands.append(_parse_number("-" + tokens[index + 1][1]))
                    index += 2
                    expecting_operand = False
                    continue
                raise ValidationError(errors=["dangling minus sign"])
            if kind == "number":
                operands.append(_parse_number(payload))
                index += 1
                expecting_operand = False
                continue
            if kind == "function":
                function_name, arguments = payload
                operands.append((_apply_function(function_name, arguments), False))
                index += 1
                expecting_operand = False
                continue
            raise ValidationError(errors=["expected a value"])
        if kind == "operator":
            operators.append(payload)
            index += 1
            expecting_operand = True
            continue
        raise ValidationError(errors=["expected an operator between values"])
    if expecting_operand:
        raise ValidationError(errors=["expression ends without a value"])
    return operands, operators


def _parse_number(literal: str) -> tuple[Decimal, bool]:
    is_percent = literal.endswith("%")
    numeric_literal = literal[:-1] if is_percent else literal
    _validate_digit_count(numeric_literal)
    try:
        return Decimal(numeric_literal), is_percent
    except _DecimalInvalidOperation as error:
        raise ValidationError(errors=[f"invalid number: {literal}"]) from error


def _validate_digit_count(literal: str) -> None:
    digit_count = sum(1 for character in literal if character.isdigit())
    if digit_count > _MAX_DIGITS_PER_VALUE:
        raise ValidationError(
            errors=[f"value exceeds the {_MAX_DIGITS_PER_VALUE}-digit limit"]
        )


def _apply_function(name: str, raw_arguments: str) -> Decimal:
    if name not in _ALLOWED_FUNCTIONS:
        raise ValidationError(errors=[f"unknown function: {name}"])
    arguments = _parse_function_arguments(raw_arguments)
    try:
        if name == "sqrt":
            return _sqrt(_single_argument(name, arguments))
        if name == "ln":
            return _ln(_single_argument(name, arguments))
        if name == "log10":
            return _log10(_single_argument(name, arguments))
        return _log_base(name, arguments)
    except _DecimalInvalidOperation as error:
        raise MathDomainError(errors=[f"{name}: invalid operand"]) from error


def _parse_function_arguments(raw_arguments: str) -> list[Decimal]:
    pieces = [piece.strip() for piece in raw_arguments.split(",")]
    if not raw_arguments.strip() or any(not piece for piece in pieces):
        raise ValidationError(errors=["function call with empty argument"])
    values = []
    for piece in pieces:
        if not _FUNCTION_ARGUMENT_PATTERN.match(piece):
            # Symbolic or nested arguments belong to the symbolic path.
            raise ValidationError(
                errors=[f"function argument must be a numeric literal: {piece}"]
            )
        _validate_digit_count(piece)
        values.append(Decimal(piece))
    return values


def _single_argument(name: str, arguments: list[Decimal]) -> Decimal:
    if len(arguments) != 1:
        raise ValidationError(errors=[f"{name} takes exactly one argument"])
    return arguments[0]


def _sqrt(value: Decimal) -> Decimal:
    if value < 0:
        raise MathDomainError(errors=["square root of a negative number"])
    return value.sqrt()


def _ln(value: Decimal) -> Decimal:
    if value <= 0:
        raise MathDomainError(errors=["logarithm of zero or a negative number"])
    return value.ln()


def _log10(value: Decimal) -> Decimal:
    if value <= 0:
        raise MathDomainError(errors=["logarithm of zero or a negative number"])
    return value.log10()


def _log_base(name: str, arguments: list[Decimal]) -> Decimal:
    if len(arguments) != 2:
        raise ValidationError(errors=[f"{name} takes exactly two arguments"])
    value, base = arguments
    if value <= 0:
        raise MathDomainError(errors=["logarithm of zero or a negative number"])
    if base <= 0 or base == 1:
        raise MathDomainError(errors=["logarithm base must be positive and != 1"])
    # Fixed contract: log(x, base) = ln(x) / ln(base).
    return value.ln() / base.ln()


def _fold(operands: list[tuple[Decimal, bool]], operators: list[str]) -> Decimal:
    first_value, first_is_percent = operands[0]
    accumulator = first_value / _ONE_HUNDRED if first_is_percent else first_value
    for operator, (value, is_percent) in zip(operators, operands[1:]):
        accumulator = _apply_operator(accumulator, operator, value, is_percent)
    return accumulator


def _apply_operator(
    accumulator: Decimal, operator: str, value: Decimal, is_percent: bool
) -> Decimal:
    # Desk-calculator percent semantics: with + / - the n% operand is relative
    # to the accumulator; with * / / / ** it is the plain factor n/100.
    if is_percent:
        if operator == "+":
            return accumulator * (1 + value / _ONE_HUNDRED)
        if operator == "-":
            return accumulator * (1 - value / _ONE_HUNDRED)
        value = value / _ONE_HUNDRED
    try:
        if operator == "+":
            return accumulator + value
        if operator == "-":
            return accumulator - value
        if operator == "*":
            return accumulator * value
        if operator == "/":
            if value == 0:
                raise DivisionByZeroError(errors=["division by zero"])
            return accumulator / value
        return _apply_power(accumulator, value)
    except _DecimalDivisionByZero as error:
        raise DivisionByZeroError(errors=["division by zero"]) from error
    except _DecimalInvalidOperation as error:
        raise MathDomainError(errors=["operation outside the numeric domain"]) from error
    except _DecimalOverflow as error:
        raise ValidationError(errors=["result is too large"]) from error


def _apply_power(base: Decimal, exponent: Decimal) -> Decimal:
    # PRE-checks — the rejection must be immediate, never "compute and see if
    # it blows up".
    if abs(exponent) > _MAX_EXPONENT:
        raise ValidationError(
            errors=[f"exponent exceeds the +/-{_MAX_EXPONENT} limit"]
        )
    if base == 0 and exponent == 0:
        raise MathDomainError(errors=["0 ** 0 is indeterminate"])
    estimated_digits = (abs(base.adjusted()) + 1) * int(abs(exponent))
    if estimated_digits > _MAX_ESTIMATED_RESULT_DIGITS:
        raise ValidationError(errors=["power result would be too large"])
    return base ** exponent
