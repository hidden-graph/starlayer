"""Syntax rules the SPARQL 1.2 grammar states but rdflib's parser never
enforces, checked here on the raw text or on rdflib's parse tree, before
translation. See ``docs/upstream-issues/rdflib-upstream-issues.md`` items 13
and 14 for a minimal example of each.

Not covered: a ``\\uXXXX`` escape spelling a keyword, and a ``SELECT``
expression variable that is already in scope in the ``WHERE`` pattern.
(``BIND`` onto an in-scope variable, ``SELECT *`` with grouping, and the
``TripleTermData`` form of a ``VALUES`` triple term are checked below.)
"""

from __future__ import annotations

import re

from rdflib import BNode, Variable
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
        elif node.name in ("SelectQuery", "SubSelect"):
            _check_group_by_scope(node)
            _check_select_star_grouping(node)
        elif node.name == "GroupGraphPatternSub":
            _check_bind_scope(node)
        if node.name == "InlineData":
            for inner in _walk(_as_list(node.get("value"))):
                if inner.name == "TripleTerm":
                    _check_triple_term_data(inner)
        elif node.name == "Bind":
            for inner in _walk(node.get("expr")):
                if inner.name == "TripleTerm":
                    _check_expr_triple_term(inner)


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


def _check_select_star_grouping(select: CompValue) -> None:
    """``SELECT *`` is not permitted with ``GROUP BY`` or with aggregates in
    ``HAVING``/``ORDER BY`` (SPARQL 1.2 Query 16.1.1)."""
    if isinstance(select.get("projection"), (list, tuple)) or hasattr(select.get("projection"), "asList"):
        return
    grouped = isinstance(select.get("groupby"), CompValue)
    for key in ("having", "orderby"):
        if any(n.name.startswith("Aggregate_") for n in _walk(select.get(key))):
            grouped = True
    if grouped:
        raise SPARQLSyntaxError("SELECT * is not permitted with GROUP BY or with aggregates in HAVING or ORDER BY")


# Parts of a group pattern that bind nothing visible to a later BIND.
_NOT_IN_SCOPE = ("Filter", "MinusGraphPattern")


def _scope_variables(node, out: set) -> None:
    """Variables in scope after ``node`` (SPARQL 1.2 Query 18.2.1): not those
    only in a FILTER or the right side of MINUS; a BIND contributes its target
    only; a sub-select its explicit projection."""
    if isinstance(node, Variable):
        out.add(node)
    elif isinstance(node, CompValue):
        if node.name in _NOT_IN_SCOPE:
            return
        if node.name == "Bind":
            if isinstance(node.get("var"), Variable):
                out.add(node["var"])
            return
        if node.name in ("SelectQuery", "SubSelect"):
            for item in _as_list(node.get("projection")):
                if isinstance(item, CompValue):
                    item = item.get("var") if isinstance(item.get("var"), Variable) else item.get("evar")
                if isinstance(item, Variable):
                    out.add(item)
            return
        for value in node.values():
            _scope_variables(value, out)
    elif isinstance(node, (list, tuple)) or hasattr(node, "asList"):
        for item in node:
            _scope_variables(item, out)


def _check_bind_scope(group: CompValue) -> None:
    """The variable a ``BIND`` introduces must not be in scope in the group
    pattern before it (SPARQL 1.2 Query 10.1)."""
    seen: set = set()
    for part in _as_list(group.get("part")):
        if isinstance(part, CompValue) and part.name == "Bind":
            target = part.get("var")
            if isinstance(target, Variable) and target in seen:
                raise SPARQLSyntaxError(f"BIND target ?{target} is already in scope before the BIND")
        _scope_variables(part, seen)


def _check_triple_term_data(tt: CompValue) -> None:
    """A ``VALUES`` triple term is ``TripleTermData``: IRI subject, IRI
    predicate, and an IRI, literal or nested ``TripleTermData`` object; no
    variable and no blank node (grammar rules 122-124)."""
    subject, predicate, obj = tt.get("subject"), tt.get("predicate"), tt.get("object")
    for term in (subject, predicate, obj):
        if isinstance(term, (Variable, BNode)):
            raise SPARQLSyntaxError("a VALUES triple term cannot contain a variable or a blank node")
    if isinstance(subject, CompValue) and subject.name != "pname":
        raise SPARQLSyntaxError("the subject of a VALUES triple term must be an IRI")
    if isinstance(obj, CompValue) and obj.name == "TripleTerm":
        _check_triple_term_data(obj)


def _check_expr_triple_term(tt: CompValue) -> None:
    """In an expression, a triple term's subject is an IRI or variable and its
    object is not a blank node (ExprTripleTerm, grammar rules 137-139)."""
    if isinstance(tt.get("subject"), BNode) or isinstance(tt.get("object"), BNode):
        raise SPARQLSyntaxError("a blank node is not allowed in a triple term in an expression")
    obj = tt.get("object")
    if isinstance(obj, CompValue) and obj.name == "TripleTerm":
        _check_expr_triple_term(obj)
