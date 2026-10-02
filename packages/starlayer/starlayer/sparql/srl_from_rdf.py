"""Decode ``srl:`` RDF back into a ``starlayer.sparql.srl_ast`` tree - the
inverse of ``srl_to_rdf.py``, following the same "delegate every term/
expression leaf to the existing generic decoder, only ``srl:``-specific
container shapes get bespoke code" split.
"""

from __future__ import annotations

from rdflib import RDF, Graph
from rdflib.collection import Collection

from . import srl_ast
from .from_rdf import _decode
from .srl_vocab import (
    ASSIGNMENT_ELEMENT,
    BODY,
    DATA,
    DATA_BLOCK,
    EXPR,
    FILTER_ELEMENT,
    HEAD,
    IMPORTS,
    INNER,
    NEGATION_DATA_FLAG,
    NEGATION_ELEMENT,
    RULE,
    RULE_DATA_FLAG,
    RULE_ID,
    RULES,
    TRIPLE_OBJECT,
    TRIPLE_PATTERN,
    TRIPLE_PREDICATE,
    TRIPLE_SUBJECT,
    TRIPLES,
    VAR,
)


class SRLDecodeError(ValueError):
    """Raised for an ``srl:`` graph shape ``rdf_to_ruleset`` doesn't recognize."""


def _rdf_list(node, graph: Graph) -> list:
    if node == RDF.nil:
        return []
    return list(Collection(graph, node))


def _decode_triple(node, graph: Graph) -> srl_ast.TriplePattern:
    return srl_ast.TriplePattern(
        subject=_decode(graph.value(node, TRIPLE_SUBJECT), graph),
        predicate=_decode(graph.value(node, TRIPLE_PREDICATE), graph),
        object=_decode(graph.value(node, TRIPLE_OBJECT), graph),
    )


def _node_type(node, graph: Graph):
    return graph.value(node, RDF.type)


def _decode_body_element(node, graph: Graph) -> srl_ast.BodyElement:
    t = _node_type(node, graph)
    if t == TRIPLE_PATTERN:
        return _decode_triple(node, graph)
    if t == FILTER_ELEMENT:
        return srl_ast.FilterElement(expr=_decode(graph.value(node, EXPR), graph))
    if t == ASSIGNMENT_ELEMENT:
        return srl_ast.AssignmentElement(
            var=_decode(graph.value(node, VAR), graph),
            expr=_decode(graph.value(node, EXPR), graph),
        )
    if t == NEGATION_ELEMENT:
        inner = [_decode_body_element(n, graph) for n in _rdf_list(graph.value(node, INNER), graph)]
        data_flag = bool(_decode(graph.value(node, NEGATION_DATA_FLAG), graph))
        return srl_ast.NegationElement(inner=inner, data=data_flag)
    raise SRLDecodeError(f"unrecognized rule body element node {node!r} (rdf:type {t!r})")


def _decode_rule(node, graph: Graph) -> srl_ast.Rule:
    head = [_decode_triple(n, graph) for n in _rdf_list(graph.value(node, HEAD), graph)]
    body = [_decode_body_element(n, graph) for n in _rdf_list(graph.value(node, BODY), graph)]
    data_flag = bool(_decode(graph.value(node, RULE_DATA_FLAG), graph))
    rule_id = graph.value(node, RULE_ID)
    return srl_ast.Rule(head=head, body=body, data=data_flag, id=rule_id)


def _decode_data(node, graph: Graph) -> srl_ast.Data:
    triples = [_decode_triple(n, graph) for n in _rdf_list(graph.value(node, TRIPLES), graph)]
    return srl_ast.Data(triples=triples)


def rdf_to_ruleset(graph: Graph, root) -> srl_ast.RuleSet:
    """Inverse of ``srl_to_rdf.ruleset_to_rdf`` - decode the ``srl:RuleSet``
    node ``root`` in ``graph`` back into a real ``srl_ast.RuleSet``."""
    rules = [_decode_rule(n, graph) for n in _rdf_list(graph.value(root, RULES), graph)]
    data = [_decode_data(n, graph) for n in _rdf_list(graph.value(root, DATA), graph)]
    imports = list(_rdf_list(graph.value(root, IMPORTS), graph))
    return srl_ast.RuleSet(rules=rules, data=data, imports=imports)
