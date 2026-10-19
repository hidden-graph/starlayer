"""Shared helpers for the SRL conformance suite."""

from __future__ import annotations

import functools
import itertools
import re

from rdflib import Graph, Literal, URIRef, Variable
from rdflib.plugins.sparql.parserutils import value
from rdflib.plugins.sparql.sparql import FrozenBindings, QueryContext
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

__all__ = ["canonical_blank_nodes", "expression_results", "isomorphic", "parse_ruleset", "parsed", "ruleset_to_text", "ruleset_to_tree",
           "srl_parse_to_tree", "srl_tree_to_text", "srl_validate", "tree_of"]


@functools.cache
def parsed(text: str):
    """``parse_ruleset(text)`` (with its section 4.2 check and shape validation), cached: the same text is
    parsed by several tests and validation costs ~140 ms."""
    return parse_ruleset(text)


_BNODE_LABEL = re.compile(r"_:N[0-9a-f]{32}")


def canonical_blank_nodes(text: str) -> str:
    """``text`` with parser-minted blank-node labels (``_:N<32 hex>``) renamed ``_:b0``, ``_:b1``... in order of
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


_VALUES = (Literal(1), Literal(2), Literal(-3), Literal(2.5), Literal("a"), Literal(True), URIRef("http://example.org/c"))


def expression_results(ruleset) -> list:
    """What every FILTER / SET expression of ``ruleset`` evaluates to under a grid of bindings.

    Used to check that text -> AST -> text -> AST preserves *meaning*, not just shape: a renderer that drops
    parentheses produces text that parses fine and means something else. Errors are results too (a SPARQL
    error is part of an expression's meaning), recorded by exception type.
    """
    context = QueryContext(Graph())
    results = []
    for rule in ruleset.rules:
        for expression in _expressions(rule.body):
            for y, z in itertools.product(_VALUES, (Literal(3), Literal("s"))):
                bindings = FrozenBindings(context, {
                    Variable("x"): URIRef("http://example.org/a"), Variable("y"): y, Variable("z"): z,
                    Variable("w"): Literal(2),
                })
                try:
                    results.append(repr(value(bindings, expression, variables=False)))
                except Exception as error:  # noqa: BLE001
                    results.append(f"error:{type(error).__name__}")
    return results
