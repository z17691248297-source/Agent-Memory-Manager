from __future__ import annotations

import ast
import operator
import re


OPS = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.USub: operator.neg,
}


def calculate(input_text: str, context: dict | None = None) -> str:
    expr = _extract_expr(input_text)
    value = _safe_eval(expr)
    return f"表达式: {expr}\n结果: {value}"


def _extract_expr(text: str) -> str:
    matches = re.findall(r"[0-9+\-*/().\s]+", text)
    expr = max(matches, key=len).strip() if matches else ""
    if not expr:
        raise ValueError("未找到可计算表达式")
    return expr


def _safe_eval(expr: str) -> float:
    node = ast.parse(expr, mode="eval")
    return float(_eval_node(node.body))


def _eval_node(node: ast.AST) -> float:
    if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)):
        return float(node.value)
    if isinstance(node, ast.BinOp) and type(node.op) in OPS:
        return OPS[type(node.op)](_eval_node(node.left), _eval_node(node.right))
    if isinstance(node, ast.UnaryOp) and type(node.op) in OPS:
        return OPS[type(node.op)](_eval_node(node.operand))
    raise ValueError("只支持安全的四则运算")

