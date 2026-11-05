"""Shared helpers for the SRL conformance suite."""

from __future__ import annotations

import functools
import itertools
import re

import pyoxigraph as ox
from starlayer.graph.compare import isomorphic
from starlayer.sparql._srl_ast import (
    _AssignmentElement,
    _FilterElement,
    _NegationElement,
)
from starlayer.sparql.srl import (
    parse_ruleset,
    ruleset_to_text,
    ruleset_to_tree,
    srl_parse_to_tree,
    srl_tree_to_text,
    srl_validate,
)
from starlayer.sparql.srl_eval import _eval_expr

__all__ = ["canonical_blank_nodes", "expression_results", "isomorphic", "parse_ruleset", "parsed", "ruleset_to_text", "ruleset_to_tree",
           "srl_parse_to_tree", "srl_tree_to_text", "srl_validate", "tree_of", "as_stored"]


@functools.cache
def parsed(text: str):
    """``parse_ruleset(text)`` (with its section 4.2 check and shape validation), cached: the same text is
    parsed by several tests and validation costs ~140 ms."""
    return parse_ruleset(text)


_BNODE_LABEL = re.compile(r"_:[0-9a-f]{28,32}")


def canonical_blank_nodes(text: str) -> str:
    """``text`` with parser-minted blank-node labels (``_:<32 hex>``) renamed ``_:b0``, ``_:b1``... in order of
    first appearance. Two parses of the same source mint different labels, so texts are only comparable after this."""
    seen: dict[str, str] = {}
    return _BNODE_LABEL.sub(lambda m: seen.setdefault(m.group(0), f"_:b{len(seen)}"), text)


def tree_of(ruleset):
    """The ``srl:`` tree graph of a ruleset (without the root)."""
    graph, _root = ruleset_to_tree(ruleset)
    return graph


def _expressions(elements):
    for element in elements:
        if isinstance(element, (_FilterElement, _AssignmentElement)):
            yield element.expr
        elif isinstance(element, _NegationElement):
            yield from _expressions(element.inner)


_XSD = "http://www.w3.org/2001/XMLSchema#"
_VALUES = (
    ox.Literal("1", datatype=ox.NamedNode(_XSD + "integer")),
    ox.Literal("2", datatype=ox.NamedNode(_XSD + "integer")),
    ox.Literal("-3", datatype=ox.NamedNode(_XSD + "integer")),
    ox.Literal("2.5", datatype=ox.NamedNode(_XSD + "decimal")),
    ox.Literal("a"),
    ox.Literal("true", datatype=ox.NamedNode(_XSD + "boolean")),
    ox.NamedNode("http://example.org/c"),
)


def expression_results(ruleset) -> list:
    """What every FILTER / SET expression of ``ruleset`` evaluates to under a grid of bindings.

    Used to check that text -> AST -> text -> AST preserves *meaning*, not just shape: a renderer that drops
    parentheses produces text that parses fine and means something else. Evaluated by the SRL evaluator's own expression
    path (Oxigraph); an error is a result too (a SPARQL error is part of an expression's meaning), recorded as ``None``.
    """
    results = []
    for rule in ruleset.rules:
        for expression in _expressions(rule.body):
            for y, z in itertools.product(_VALUES, (ox.Literal("3", datatype=ox.NamedNode(_XSD + "integer")), ox.Literal("s"))):
                bindings = {
                    ox.Variable("x"): ox.NamedNode("http://example.org/a"), ox.Variable("y"): y, ox.Variable("z"): z,
                    ox.Variable("w"): ox.Literal("2", datatype=ox.NamedNode(_XSD + "integer")),
                }
                try:
                    results.append(repr(_eval_expr(expression, bindings)))
                except Exception as error:  # noqa: BLE001 - an error is part of an expression's meaning (e.g. an unsupported custom function)
                    results.append(f"error:{type(error).__name__}")
    return results


def _stored_literal(term):
    """The literal as an Oxigraph-backed graph holds it (``"9.0"^^xsd:decimal`` is kept ``"9"``; ``.5`` is ``0.5``)."""
    from starlayer.graph.oxgraph.core import StarLayerGraph

    g = StarLayerGraph(prefixes={})
    g.add((ox.NamedNode("urn:s"), ox.NamedNode("urn:p"), term))
    return next(iter(g))[2]


def _stored(value):
    from starlayer.sparql._srl_ast import TriplePattern
    from starlayer.sparql.parse_sparql import Node

    if isinstance(value, ox.Literal):
        return _stored_literal(value)
    if isinstance(value, Node):
        node = type(value)(value.kind, **{k: _stored(v) for k, v in value.f.items()})
        return node
    if isinstance(value, list):
        return [_stored(v) for v in value]
    if isinstance(value, TriplePattern):
        return TriplePattern(_stored(value.subject), value.predicate, _stored(value.object))
    if isinstance(value, _FilterElement):
        return _FilterElement(expr=_stored(value.expr))
    if isinstance(value, _AssignmentElement):
        return _AssignmentElement(var=value.var, expr=_stored(value.expr))
    if isinstance(value, _NegationElement):
        return _NegationElement(inner=_stored(value.inner), evaldata=value.evaldata)
    return value


def as_stored(ruleset):
    """``ruleset`` with every literal in the form the store keeps it. A rule set read back from its ``srl:`` tree (a
    ``StarLayerGraph``) has the literals this way, so that is what to compare a tree round trip with."""
    from dataclasses import replace

    from starlayer.sparql._srl_ast import _Data, _Rule

    rules = [_Rule(head=_stored(r.head), body=_stored(r.body), evaldata=r.evaldata, id=r.id) for r in ruleset.rules]
    data = [_Data(triples=_stored(d.triples)) for d in ruleset.data]
    return replace(ruleset, rules=rules, data=data)
