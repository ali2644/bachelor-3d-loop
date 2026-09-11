from __future__ import annotations

import ast
import math
import operator
from typing import Mapping


MAX_EXPRESSION_LENGTH = 256
MAX_AST_NODES = 64
SUPPORTED_VARIABLES = frozenset(
    {
        "Ra_um",
        "Rz_um",
        "print_time",
        "print_time_seconds",
        "print_time_minutes",
    }
)


class ObjectiveExpressionError(ValueError):
    """Raised when an objective expression is unsafe or cannot be evaluated."""


_BINARY_OPERATORS = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.Pow: operator.pow,
}
_UNARY_OPERATORS = {
    ast.UAdd: operator.pos,
    ast.USub: operator.neg,
}


def validate_objective_expression(expression: str) -> frozenset[str]:
    """Validate safe arithmetic and return the referenced metric names."""
    tree = _parse(expression)
    referenced: set[str] = set()
    nodes = list(ast.walk(tree))
    if len(nodes) > MAX_AST_NODES:
        raise ObjectiveExpressionError(
            f"objective expression is too complex (maximum {MAX_AST_NODES} nodes)."
        )

    allowed_node_types = (
        ast.Expression,
        ast.BinOp,
        ast.UnaryOp,
        ast.Name,
        ast.Load,
        ast.Constant,
        *tuple(_BINARY_OPERATORS),
        *tuple(_UNARY_OPERATORS),
    )
    for node in nodes:
        if not isinstance(node, allowed_node_types):
            raise ObjectiveExpressionError(
                "objective may only contain numbers, metric names, parentheses "
                "and the operators +, -, *, / and **."
            )
        if isinstance(node, ast.Name):
            if node.id not in SUPPORTED_VARIABLES:
                supported = ", ".join(sorted(SUPPORTED_VARIABLES))
                raise ObjectiveExpressionError(
                    f"unknown objective variable {node.id!r}. Use: {supported}."
                )
            referenced.add(node.id)
        if isinstance(node, ast.Constant):
            if isinstance(node.value, bool) or not isinstance(
                node.value, (int, float)
            ):
                raise ObjectiveExpressionError(
                    "objective constants must be finite numbers."
                )
            try:
                value = float(node.value)
            except (OverflowError, ValueError) as error:
                raise ObjectiveExpressionError(
                    "objective constants must be finite numbers."
                ) from error
            if not math.isfinite(value):
                raise ObjectiveExpressionError(
                    "objective constants must be finite numbers."
                )

    if not referenced:
        raise ObjectiveExpressionError(
            "objective must reference at least one measured metric."
        )
    return frozenset(referenced)


def evaluate_objective_expression(
    expression: str,
    *,
    ra_um: float | None,
    rz_um: float | None,
    print_time_seconds: float | None,
) -> float:
    """Evaluate one validated expression using measurements from a run."""
    referenced = validate_objective_expression(expression)
    values: Mapping[str, float | None] = {
        "Ra_um": ra_um,
        "Rz_um": rz_um,
        "print_time": print_time_seconds,
        "print_time_seconds": print_time_seconds,
        "print_time_minutes": (
            None
            if print_time_seconds is None
            else float(print_time_seconds) / 60.0
        ),
    }
    normalized: dict[str, float] = {}
    for name in referenced:
        raw_value = values[name]
        if raw_value is None:
            raise ObjectiveExpressionError(
                f"objective requires {name!r}, but this run did not produce it."
            )
        value = float(raw_value)
        if not math.isfinite(value):
            raise ObjectiveExpressionError(
                f"objective variable {name!r} must be finite."
            )
        normalized[name] = value

    try:
        result = _evaluate_node(_parse(expression).body, normalized)
    except ZeroDivisionError as error:
        raise ObjectiveExpressionError(
            "objective expression divided by zero."
        ) from error
    except (OverflowError, TypeError, ValueError) as error:
        raise ObjectiveExpressionError(
            f"objective expression could not be evaluated: {error}"
        ) from error
    if not math.isfinite(result):
        raise ObjectiveExpressionError(
            "objective expression produced a non-finite result."
        )
    return result


def _parse(expression: str) -> ast.Expression:
    if not isinstance(expression, str) or not expression.strip():
        raise ObjectiveExpressionError("objective must be non-empty text.")
    if len(expression) > MAX_EXPRESSION_LENGTH:
        raise ObjectiveExpressionError(
            "objective expression is too long "
            f"(maximum {MAX_EXPRESSION_LENGTH} characters)."
        )
    try:
        parsed = ast.parse(expression, mode="eval")
    except SyntaxError as error:
        raise ObjectiveExpressionError(
            f"invalid objective expression: {error.msg}."
        ) from error
    assert isinstance(parsed, ast.Expression)
    return parsed


def _evaluate_node(node: ast.AST, values: Mapping[str, float]) -> float:
    if isinstance(node, ast.Constant):
        return float(node.value)
    if isinstance(node, ast.Name):
        return values[node.id]
    if isinstance(node, ast.BinOp):
        function = _BINARY_OPERATORS[type(node.op)]
        return float(
            function(
                _evaluate_node(node.left, values),
                _evaluate_node(node.right, values),
            )
        )
    if isinstance(node, ast.UnaryOp):
        function = _UNARY_OPERATORS[type(node.op)]
        return float(function(_evaluate_node(node.operand, values)))
    raise ObjectiveExpressionError("unsupported objective expression element.")
