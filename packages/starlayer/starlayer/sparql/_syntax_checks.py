"""Syntax rules the SPARQL 1.2 grammar states but rdflib's parser never
enforces, checked here on the raw text or on rdflib's parse tree, before
translation. See ``docs/upstream-issues/rdflib-upstream-issues.md`` items 13
and 14 for a minimal example of each.

Not covered: a ``\\uXXXX`` escape spelling a keyword, and a ``SELECT``
expression variable that is already in scope in the ``WHERE`` pattern.
"""

from __future__ import annotations

import re

from rdflib import Variable
from rdflib.plugins.sparql.parserutils import CompValue


class SPARQLSyntaxError(ValueError):
    """A query or update breaks a SPARQL grammar rule that rdflib accepts."""


# `\\` is consumed as a pair so an escaped backslash followed by "uD800" is not read as an escape.
_ESCAPE = re.compile(r"\\(?:\\|u([0-9A-Fa-f]{4}))")


def reject_surrogate_escapes(text: str) -> None:
    """Reject a ``\\uD800``-``\\uDFFF`` codepoint escape.

    A surrogate is not a Unicode scalar value, so SPARQL 1.2 forbids it even
    as half of a valid pair; a character outside the BMP is written
    ``\\UXXXXXXXX``.

    Raises:
        SPARQLSyntaxError: If ``text`` contains such an escape.
    """
    for match in _ESCAPE.finditer(text):
        digits = match.group(1)
        if digits is not None and 0xD800 <= int(digits, 16) <= 0xDFFF:
            raise SPARQLSyntaxError(
                f"\\u{digits} is a surrogate, not a Unicode scalar value; use \\UXXXXXXXX"
            )


def _walk(node):
    """Yield every ``CompValue`` under ``node`` (including ``node``)."""
    if isinstance(node, CompValue):
        yield node
        for value in node.values():
            yield from _walk(value)
    elif isinstance(node, (list, tuple)) or hasattr(node, "asList"):
        for item in node:
            yield from _walk(item)


def _as_list(value) -> list:
    if value is None or isinstance(value, str) and not isinstance(value, Variable):
        return []  # CompValue.get() returns a bare str for an absent key
    return (
        list(value)
        if isinstance(value, (list, tuple)) or hasattr(value, "asList")
        else [value]
    )


def check_parse_tree(tree) -> None:
    """Reject nested aggregates, a repeated ``VALUES`` variable, and a
    ``SELECT`` expression variable that reuses a ``GROUP BY`` key's name.

    Raises:
        SPARQLSyntaxError: On the first rule broken.
    """
    for node in _walk(tree):
        if node.name.startswith("Aggregate_"):
            for inner in _walk(list(node.values())):
                if inner.name.startswith("Aggregate_"):
                    raise SPARQLSyntaxError(
                        "an aggregate function cannot be nested inside another aggregate"
                    )
        elif node.name == "InlineData":
            names = [str(v) for v in _as_list(node.get("var"))]
            if len(names) != len(set(names)):
                raise SPARQLSyntaxError("a VALUES clause cannot repeat a variable")
        elif node.name == "SelectQuery":
            _check_group_by_scope(node)


def _check_group_by_scope(select: CompValue) -> None:
    group = select.get("groupby")
    if not isinstance(group, CompValue):
        return
    keys: set[str] = set()
    for condition in _as_list(group.get("condition")):
        if isinstance(condition, Variable):
            keys.add(str(condition))
        elif (
            isinstance(condition, CompValue)
            and condition.name == "GroupAs"
            and isinstance(condition.get("var"), Variable)
        ):
            keys.add(str(condition["var"]))
    for item in _as_list(select.get("projection")):
        target = item.get("evar") if isinstance(item, CompValue) else None
        if isinstance(target, Variable) and str(target) in keys:
            raise SPARQLSyntaxError(
                f"SELECT expression variable ?{target} is already a GROUP BY key"
            )
