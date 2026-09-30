"""Encode a ``starsparql.srl_ast`` tree as ``srl:`` RDF - see
``srl_vocab.py``'s module docstring for the field-name/list-valued-field
conventions this follows (taken verbatim from the spec's own §4.1
"Component Notation" table).

Every term (``Variable``/``URIRef``/``BNode``/``Literal``/``TripleTermNode``)
and every expression tree (``filter.expr``/``assign.expr``, a real rdflib
``Expr``) is encoded by delegating straight to ``to_rdf._encode`` - it
already handles all of these uniformly (a ``TripleTermNode``/``Expr`` is
just another ``CompValue`` to it), so this module only needs bespoke logic
for the container shapes ``to_rdf.py`` has never seen: ``RuleSet``/
``Rule``/``Data``/``TriplePattern``/``FilterElement``/``NegationElement``/
``AssignmentElement``.
"""

from __future__ import annotations

from rdflib import RDF, BNode, Graph, URIRef
from rdflib.collection import Collection

from . import srl_ast
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
    RULE_SET,
    RULES,
    TRIPLE_OBJECT,
    TRIPLE_PATTERN,
    TRIPLE_PREDICATE,
    TRIPLE_SUBJECT,
    TRIPLES,
    VAR,
)
from .to_rdf import _encode, _new_starlayer_graph


def ruleset_to_rdf(ruleset: srl_ast.RuleSet, graph: Graph | None = None) -> tuple[Graph, BNode]:
    """Encode a whole rule set. Returns ``(graph, root)``, ``root`` the
    ``srl:RuleSet``-typed node."""
    if graph is None:
        graph = _new_starlayer_graph()
    root = BNode()
    graph.add((root, RDF.type, RULE_SET))
    graph.add((root, RULES, _rdf_list(graph, [_rule_to_rdf(r, graph) for r in ruleset.rules])))
    graph.add((root, DATA, _rdf_list(graph, [_data_to_rdf(d, graph) for d in ruleset.data])))
    graph.add((root, IMPORTS, _rdf_list(graph, list(ruleset.imports))))
    return graph, root


def _rdf_list(graph: Graph, items: list) -> BNode | URIRef:
    if not items:
        return RDF.nil
    list_node = BNode()
    Collection(graph, list_node, items)
    return list_node


def _triple_to_rdf(triple: srl_ast.TriplePattern, graph: Graph) -> BNode:
    node = BNode()
    graph.add((node, RDF.type, TRIPLE_PATTERN))
    graph.add((node, TRIPLE_SUBJECT, _encode(triple.subject, graph)))
    graph.add((node, TRIPLE_PREDICATE, _encode(triple.predicate, graph)))
    graph.add((node, TRIPLE_OBJECT, _encode(triple.object, graph)))
    return node


def _body_element_to_rdf(element: srl_ast.BodyElement, graph: Graph) -> BNode:
    if isinstance(element, srl_ast.TriplePattern):
        return _triple_to_rdf(element, graph)
    if isinstance(element, srl_ast.FilterElement):
        node = BNode()
        graph.add((node, RDF.type, FILTER_ELEMENT))
        graph.add((node, EXPR, _encode(element.expr, graph)))
        return node
    if isinstance(element, srl_ast.AssignmentElement):
        node = BNode()
        graph.add((node, RDF.type, ASSIGNMENT_ELEMENT))
        graph.add((node, VAR, _encode(element.var, graph)))
        graph.add((node, EXPR, _encode(element.expr, graph)))
        return node
    if isinstance(element, srl_ast.NegationElement):
        node = BNode()
        graph.add((node, RDF.type, NEGATION_ELEMENT))
        inner_nodes = [_body_element_to_rdf(e, graph) for e in element.inner]
        graph.add((node, INNER, _rdf_list(graph, inner_nodes)))
        graph.add((node, NEGATION_DATA_FLAG, _encode(element.data, graph)))
        return node
    raise NotImplementedError(f"starsparql.srl_to_rdf: no encoding for body element {element!r}")  # pragma: no cover


def _rule_to_rdf(rule: srl_ast.Rule, graph: Graph) -> BNode:
    node = BNode()
    graph.add((node, RDF.type, RULE))
    head_nodes = [_triple_to_rdf(t, graph) for t in rule.head]
    graph.add((node, HEAD, _rdf_list(graph, head_nodes)))
    body_nodes = [_body_element_to_rdf(e, graph) for e in rule.body]
    graph.add((node, BODY, _rdf_list(graph, body_nodes)))
    graph.add((node, RULE_DATA_FLAG, _encode(rule.data, graph)))
    if rule.id is not None:
        graph.add((node, RULE_ID, rule.id))
    return node


def _data_to_rdf(data: srl_ast.Data, graph: Graph) -> BNode:
    node = BNode()
    graph.add((node, RDF.type, DATA_BLOCK))
    triple_nodes = [_triple_to_rdf(t, graph) for t in data.triples]
    graph.add((node, TRIPLES, _rdf_list(graph, triple_nodes)))
    return node
