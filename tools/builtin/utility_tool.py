"""Safe math evaluation tool (Phase 15.1) — GREEN, no eval().

A strict AST whitelist is the only thing that ever runs: unknown nodes
(imports, calls outside the allowlist, attribute access, subscripts, names
outside pi/e) are rejected before evaluation. stdlib only, no SymPy/numpy.
"""

import ast
import math
import operator
from typing import Any, Dict, Optional, Type
from pydantic import BaseModel, Field

from core.contracts.enums import ParamKind, SecurityLevel
from core.contracts.tool import BaseTool, ToolResult

_MAX_EXPRESSION_LENGTH = 500
_MAX_AST_DEPTH = 20
_MAX_INT_EXPONENT = 1000

_ALLOWED_BINOPS = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.FloorDiv: operator.floordiv,
    ast.Mod: operator.mod,
    ast.Pow: operator.pow,
}
_ALLOWED_UNARYOPS = {ast.UAdd: operator.pos, ast.USub: operator.neg}
_ALLOWED_FUNCTIONS = {
    "abs": abs,
    "round": round,
    "sqrt": math.sqrt,
    "sin": math.sin,
    "cos": math.cos,
    "tan": math.tan,
    "log": math.log,
    "log10": math.log10,
    "exp": math.exp,
    "floor": math.floor,
    "ceil": math.ceil,
}
_ALLOWED_CONSTANTS = {"pi": math.pi, "e": math.e}


class MathEvaluationError(ValueError):
    """Raised when an expression violates the safe-evaluation rules."""


def _ast_depth(node: ast.AST) -> int:
    """Depth of an AST (1 for a leaf)."""
    children = list(ast.iter_child_nodes(node))
    if not children:
        return 1
    return 1 + max(_ast_depth(child) for child in children)


def _check_pow_exponent(node: ast.AST) -> None:
    """Reject statically huge integer exponents (DoS guard, e.g. 10**10**8)."""
    for child in ast.walk(node):
        if isinstance(child, ast.BinOp) and isinstance(child.op, ast.Pow):
            right = child.right
            if isinstance(right, ast.Constant) and isinstance(right.value, int):
                if abs(right.value) > _MAX_INT_EXPONENT:
                    raise MathEvaluationError(
                        f"Exponent too large (max {_MAX_INT_EXPONENT})."
                    )


def _evaluate(node: ast.AST) -> Any:
    """Recursively evaluate a whitelisted AST node."""
    if isinstance(node, ast.Expression):
        return _evaluate(node.body)
    if isinstance(node, ast.Constant):
        if isinstance(node.value, bool) or not isinstance(node.value, (int, float)):
            raise MathEvaluationError(f"Only int/float literals are allowed, got {node.value!r}.")
        return node.value
    if isinstance(node, ast.BinOp):
        op = _ALLOWED_BINOPS.get(type(node.op))
        if op is None:
            raise MathEvaluationError(f"Operator {type(node.op).__name__} is not allowed.")
        return op(_evaluate(node.left), _evaluate(node.right))
    if isinstance(node, ast.UnaryOp):
        op = _ALLOWED_UNARYOPS.get(type(node.op))
        if op is None:
            raise MathEvaluationError(f"Unary operator {type(node.op).__name__} is not allowed.")
        return op(_evaluate(node.operand))
    if isinstance(node, ast.Name):
        if node.id not in _ALLOWED_CONSTANTS:
            raise MathEvaluationError(f"Name {node.id!r} is not allowed (only pi and e).")
        return _ALLOWED_CONSTANTS[node.id]
    if isinstance(node, ast.Call):
        if not isinstance(node.func, ast.Name) or node.func.id not in _ALLOWED_FUNCTIONS:
            raise MathEvaluationError("Only allowlisted math functions may be called.")
        if node.keywords:
            raise MathEvaluationError("Keyword arguments are not allowed.")
        return _ALLOWED_FUNCTIONS[node.func.id](*[_evaluate(arg) for arg in node.args])
    raise MathEvaluationError(f"Expression element {type(node).__name__} is not allowed.")


def safe_evaluate(expression: str) -> Any:
    """Parse and evaluate a math expression under the whitelist rules."""
    if not isinstance(expression, str) or not expression.strip():
        raise MathEvaluationError("Expression must be a non-empty string.")
    if len(expression) > _MAX_EXPRESSION_LENGTH:
        raise MathEvaluationError(
            f"Expression too long (max {_MAX_EXPRESSION_LENGTH} chars)."
        )
    try:
        tree = ast.parse(expression, mode="eval")
    except SyntaxError as e:
        raise MathEvaluationError(f"Invalid expression: {e}.")
    if _ast_depth(tree) > _MAX_AST_DEPTH:
        raise MathEvaluationError(f"Expression too deeply nested (max {_MAX_AST_DEPTH}).")
    _check_pow_exponent(tree)
    try:
        result = _evaluate(tree)
    except ZeroDivisionError:
        raise MathEvaluationError("Division by zero.")
    except TypeError as e:
        raise MathEvaluationError(f"Invalid function arguments: {e}.")
    except (OverflowError, ValueError) as e:
        raise MathEvaluationError(f"Math domain error: {e}.")
    if isinstance(result, bool) or not isinstance(result, (int, float)):
        raise MathEvaluationError("Expression did not produce a number.")
    if isinstance(result, float) and not math.isfinite(result):
        raise MathEvaluationError("Result is not finite.")
    if isinstance(result, int) and result.bit_length() > 100000:
        raise MathEvaluationError("Result magnitude exceeds safe limits.")
    return result


class CalculateMathArgs(BaseModel):
    expression: str = Field(..., description="Math expression, e.g. '(2 + 3) * sqrt(16)'")


class CalculateMathTool(BaseTool):
    """Evaluate a math expression safely (AST whitelist, no eval)."""

    name: str = "calculate_math"
    description: str = (
        "Evaluate a math expression safely: + - * / // % **, parentheses, "
        "abs/round/sqrt/sin/cos/tan/log/log10/exp/floor/ceil, constants pi/e."
    )
    security_level: SecurityLevel = SecurityLevel.GREEN
    args_schema: Optional[Type[BaseModel]] = CalculateMathArgs
    # The expression is parsed as math AST only — never eval()'d, never a shell input.
    param_kinds: Dict[str, ParamKind] = {"expression": ParamKind.FREE_TEXT}

    async def execute(self, **kwargs: Any) -> ToolResult:
        try:
            result = safe_evaluate(kwargs.get("expression", ""))
        except MathEvaluationError as e:
            return ToolResult.fail(error=str(e), security_level=self.security_level)
        return ToolResult.ok(
            data={
                "expression": kwargs.get("expression", ""),
                "result": result,
                "type": "int" if isinstance(result, int) else "float",
            },
            security_level=self.security_level,
        )
