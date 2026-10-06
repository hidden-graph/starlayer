"""Decode ``sqe:`` RDF back into a real, executable rdflib ``Query`` —
reconstructs the raw-parse-tree-shaped ``CompValue``s ``translateQuery``
itself expects (confirmed empirically against the real function: a
``TriplesBlock``'s/``ConstructQuery``'s own ``.template``'s triples-field
is a list of 3-element lists, concatenated then re-split into groups of 3
by ``algebra.triples()`` - a single already-grouped triple just needs its
own ``[[s, p, o]]``-wrapped entry, no different from what a one-triple
``WHERE`` clause parses to from text), then hands that to rdflib's own,
completely unmodified ``translateQuery`` — the same function
``sqe/to_rdf.py``'s encoder path, ``prepare_query_12``, and the ``sast:``
layer all already call.

Term/expression/path decoding at the ``salg:`` boundary (``sqe:expr``,
and any predicate position that's a genuine property path) reuses
``..from_rdf._decode`` directly, unchanged — it already dispatches
correctly across ``Variable``/plain term/``salg:``-encoded path/expression
uniformly, so there's nothing new to write at that boundary.
"""

from __future__ import annotations

from rdflib import BNode, Graph, Literal, URIRef, Variable
from rdflib.collection import Collection
from rdflib.namespace import RDF
from rdflib.plugins.sparql.algebra import translateQuery
from rdflib.plugins.sparql.parserutils import CompValue
from rdflib.plugins.sparql.sparql import Query

from ..from_rdf import _decode
from .vocab import (
    ASK_QUERY,
    BIND,
    BIND_VAR,
    CONSTRUCT_QUERY,
    EXPR,
    FILTER,
    OPTIONAL,
    PROJECTION,
    SELECT_QUERY,
    TEMPLATE,
    TRIPLE_PATTERN,
    TRIPLE_PATTERN_OBJECT,
    TRIPLE_PATTERN_PREDICATE,
    TRIPLE_PATTERN_SUBJECT,
    UNION,
    UNION_ALTERNATIVES,
    VARIABLE_DATATYPE,
    WHERE,
)

_QUERY_NAME_BY_ROOT_TYPE = {
    SELECT_QUERY: "SelectQuery",
    ASK_QUERY: "AskQuery",
    CONSTRUCT_QUERY: "ConstructQuery",
}


def sqe_tree_to_query(graph: Graph, root) -> Query:
    """Decode ``root`` (one of ``sqe:SelectQuery``/``sqe:AskQuery``/
    ``sqe:ConstructQuery``, as produced by
    ``to_rdf.sqe_parse_to_tree``) back into a real rdflib ``Query``.

    The returned ``Query``'s own ``.prologue`` is empty (rdflib's default,
    no prefixes) — execution never needs prefixes once every term is
    already a resolved ``URIRef``. The *original* preserved prefixes live
    on ``root`` itself (``salg:prologuePrefix``, via ``to_rdf.py``'s
    ``_encode_prologue``) and are read directly by ``to_text.py`` for
    prefix-aware rendering, not threaded through here.
    """
    query_name = _query_name_for_root(graph, root)
    where = _decode_where_group(graph.value(root, WHERE), graph)

    if query_name == "SelectQuery":
        projection = [
            CompValue("vars", var=Variable(str(v)))
            for v in Collection(graph, graph.value(root, PROJECTION))
        ]
        query = CompValue(query_name, projection=projection, where=where)
    elif query_name == "ConstructQuery":
        template_list = graph.value(root, TEMPLATE)
        template = [
            _decode_triple_pattern_fields(node, graph)
            for node in (Collection(graph, template_list) if template_list is not None else [])
        ]
        query = CompValue(query_name, template=template, where=where)
    else:  # AskQuery
        query = CompValue(query_name, where=where)

    return translateQuery([[], query])


def _query_name_for_root(graph: Graph, root) -> str:
    for root_type, name in _QUERY_NAME_BY_ROOT_TYPE.items():
        if (root, RDF.type, root_type) in graph:
            return name
    raise NotImplementedError(
        f"starlayer.sparql.sqe: {root!r} has no recognized sqe: query-form type"
    )


def _decode_where_group(list_node, graph: Graph) -> CompValue:
    """``sqe:where``'s flat ``rdf:List`` of sibling elements -> a
    ``GroupGraphPatternSub``-shaped ``CompValue`` - the inverse of
    ``to_rdf._encode_where_group``. Each ``sqe:TriplePattern`` sibling
    becomes its own ``TriplesBlock`` (one per triple, not merged into a
    shared block) - simpler and just as valid as rdflib's own parser
    output, which allows multiple consecutive ``TriplesBlock`` parts."""
    nodes = list(Collection(graph, list_node)) if list_node is not None else []
    parts = [_decode_where_element(node, graph) for node in nodes]
    return CompValue("GroupGraphPatternSub", part=parts)


def _decode_where_element(node, graph: Graph) -> CompValue:
    if (node, RDF.type, TRIPLE_PATTERN) in graph:
        s, p, o = _decode_triple_pattern_fields(node, graph)
        return CompValue("TriplesBlock", triples=[[s, p, o]])
    if (node, RDF.type, OPTIONAL) in graph:
        inner = _decode_where_group(graph.value(node, WHERE), graph)
        return CompValue("OptionalGraphPattern", graph=inner)
    if (node, RDF.type, FILTER) in graph:
        expr = _decode(graph.value(node, EXPR), graph)
        return CompValue("Filter", expr=expr)
    if (node, RDF.type, BIND) in graph:
        expr = _decode(graph.value(node, EXPR), graph)
        var = _decode(graph.value(node, BIND_VAR), graph)
        return CompValue("Bind", expr=expr, var=var)
    if (node, RDF.type, UNION) in graph:
        alt_list = graph.value(node, UNION_ALTERNATIVES)
        alts = [_decode_where_group(alt, graph) for alt in Collection(graph, alt_list)]
        return CompValue("GroupOrUnionGraphPattern", graph=alts)
    raise NotImplementedError(
        f"starlayer.sparql.sqe: cannot decode WHERE-clause element {node!r} - "
        "not a recognized sqe: node type"
    )


def _decode_triple_pattern_fields(node, graph: Graph) -> list:
    s = _decode(graph.value(node, TRIPLE_PATTERN_SUBJECT), graph)
    p = _decode(graph.value(node, TRIPLE_PATTERN_PREDICATE), graph)
    o = _decode(graph.value(node, TRIPLE_PATTERN_OBJECT), graph)
    return [s, p, o]
