import ast
import operator as op
from datetime import datetime

from langchain_core.tools import tool

_BIN = {
    ast.Add: op.add, ast.Sub: op.sub, ast.Mult: op.mul, ast.Div: op.truediv,
    ast.FloorDiv: op.floordiv, ast.Mod: op.mod, ast.Pow: op.pow,
}
_UNARY = {ast.UAdd: op.pos, ast.USub: op.neg}


def _eval(node: ast.AST):
    if (
        isinstance(node, ast.Constant)
        and isinstance(node.value, (int, float))
        and not isinstance(node.value, bool)
    ):
        return node.value
    if isinstance(node, ast.BinOp) and type(node.op) in _BIN:
        left, right = _eval(node.left), _eval(node.right)
        if isinstance(node.op, ast.Pow) and abs(right) > 100:
            raise ValueError("exponent too large")
        return _BIN[type(node.op)](left, right)
    if isinstance(node, ast.UnaryOp) and type(node.op) in _UNARY:
        return _UNARY[type(node.op)](_eval(node.operand))
    raise ValueError("unsupported expression")


@tool
def get_current_time() -> str:
    """Return the current local date and time in ISO 8601 format."""
    return datetime.now().astimezone().isoformat(timespec="seconds")


@tool
def calculator(expression: str) -> str:
    """Evaluate a basic arithmetic expression such as '(1+2)*3'. Supports + - * / // % **."""
    try:
        return str(_eval(ast.parse(expression, mode="eval").body))
    except (ValueError, SyntaxError, ZeroDivisionError, OverflowError) as exc:
        return f"error: {exc}"


TOOLS = [get_current_time, calculator]
