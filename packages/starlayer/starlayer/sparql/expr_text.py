"""Render a SPARQL expression tree (rdflib algebra ``Expr``/``CompValue``) back to text.

rdflib's ``translateAlgebra`` loses information on expressions: it drops the parentheses of arithmetic, drops the flags
argument of ``REGEX`` and ``REPLACE``, and prints ``{UnaryMinus}``, ``{Function}`` or ``{Builtin_isTRIPLE}`` placeholders for
node kinds it does not know (GitHub issue #80). This renderer walks the tree itself. It accepts both the raw parse tree (a
chain of single-child ``ConditionalOrExpression`` ... ``MultiplicativeExpression`` wrappers) and a simplified one, and
parenthesises every operator node that is an operand of another operator, so the text means what the tree means whatever the
precedence rules say.

Raises ``NotImplementedError`` for a node kind it does not handle (``EXISTS`` and the aggregates), so a caller can fall back.
"""

from __future__ import annotations

from rdflib import BNode, Literal, URIRef, Variable
from rdflib.plugins.sparql.parserutils import CompValue

_OR, _AND, _REL, _ADD, _MUL, _UNARY_LEVEL, _ATOM = 1, 2, 3, 4, 5, 6, 7
_WRAPPERS = {
    "ConditionalOrExpression": ("||", _OR),
    "ConditionalAndExpression": ("&&", _AND),
    "RelationalExpression": (None, _REL),
    "AdditiveExpression": (None, _ADD),
    "MultiplicativeExpression": (None, _MUL),
}
_UNARY = {"UnaryMinus": "-", "UnaryPlus": "+", "UnaryNot": "!"}


def _args(node: CompValue) -> list:
    out: list = []
    for key, value in dict.items(node):
        if key.startswith("_") or key == "distinct" or value is None:
            continue
        out.extend(value if isinstance(value, (list, tuple)) else [value])
    return out


def _render(node) -> tuple[str, int]:
    """(text, precedence level): an operand needs parentheses only if its level is below what its position requires."""
    if isinstance(node, Variable):
        return "?" + str(node), _ATOM
    if isinstance(node, (URIRef, Literal, BNode)):
        return node.n3(), _ATOM
    if not isinstance(node, CompValue):
        if hasattr(node, "subject"):
            return _render_triple_term(node), _ATOM
        raise NotImplementedError(f"no text rendering for expression node {node!r}")

    name = node.name
    if name == "TripleTermNode" or {"subject", "predicate", "object"} <= set(dict.keys(node)):
        return _render_triple_term(node), _ATOM

    if name in _WRAPPERS:
        symbol, level = _WRAPPERS[name]
        expr = dict.get(node, "expr")
        others = dict.get(node, "other")
        ops = dict.get(node, "op")
        if others is None:
            return _render(expr)
        if name in ("ConditionalOrExpression", "ConditionalAndExpression"):
            parts = [expr, *others]
            return f" {symbol} ".join(_operand(p, level + 1) for p in parts), level
        if name == "RelationalExpression":
            left = _operand(expr, level + 1)
            if ops in ("IN", "NOT IN"):
                return f"{left} {ops} ({', '.join(_text(o) for o in others)})", level
            return f"{left} {ops} {_operand(others, level + 1)}", level
        # additive / multiplicative: a left-associative chain held in one node
        text = _operand(expr, level)
        for op, other in zip(ops, others, strict=True):
            text = f"{text} {op} {_operand(other, level + 1)}"
        return text, level

    if name in _UNARY:
        return _UNARY[name] + _operand(dict.get(node, "expr"), _UNARY_LEVEL), _UNARY_LEVEL

    if name == "Function":
        args = dict.get(node, "expr") or []
        return dict.get(node, "iri").n3() + "(" + ", ".join(_text(a) for a in args) + ")", _ATOM

    if name.startswith("Builtin_"):
        if name in ("Builtin_EXISTS", "Builtin_NOTEXISTS"):
            raise NotImplementedError(name)
        return f"{name[len('Builtin_'):]}({', '.join(_text(a) for a in _args(node))})", _ATOM

    raise NotImplementedError(f"no text rendering for expression node {name}")


def _render_triple_term(node) -> str:
    parts = (_text(dict.get(node, p)) for p in ("subject", "predicate", "object"))
    return "<<( " + " ".join(parts) + " )>>"


def _text(node) -> str:
    return _render(node)[0]


def _operand(node, needed: int) -> str:
    text, level = _render(node)
    return text if level >= needed else f"({text})"


def render_expression(expr) -> str:
    """The text of an expression tree; ``NotImplementedError`` if it has a node kind this does not render."""
    return _text(expr)
