"""Decode ``sast:`` RDF back into a real, executable rdflib ``Query`` — the
mirror of ``to_ast_rdf.py``, feeding the reconstructed parse tree straight
into rdflib's own, completely unmodified ``translateQuery`` (the same
function ``parse12.prepare_query_12`` calls on a fresh parse).

Confirmed empirically that ``translateQuery``/``translatePrologue`` only
ever read ``q[0]``/``q[1]`` by indexing/iteration and write ``q[1] = ...``
by item assignment — a plain Python ``list`` supports all of that, so the
decoded tree never needs to reconstruct real ``pyparsing.ParseResults``
objects, just plain ``list``s standing in for them. This also matches
CLAUDE.md finding #11: rdflib's own tree-walking (``_traverse``/
``_traverseAgg``) is already generic over ``CompValue``/``list``/``tuple``/
``ParseResults`` — nothing that follows in the pipeline cares which of
those a bare sequence actually is.
"""

from __future__ import annotations

from typing import Any

from rdflib import BNode, Graph, Literal, URIRef, Variable
from rdflib.collection import Collection
from rdflib.namespace import RDF
from rdflib.plugins.sparql.algebra import translateQuery
from rdflib.plugins.sparql.parserutils import CompValue, Expr
from rdflib.plugins.sparql.sparql import Query

from .ast_vocab import PROLOGUE, PY_STR_DATATYPE, QUERY, SAST, VARIABLE_DATATYPE
from .from_rdf import _EXPR_EVALFNS

_SAST_NS = str(SAST)
_AUXILIARY_ROOT_MARKERS = {QUERY}


def rdf_ast_to_query(graph: Graph, root) -> Query:
    """Decode ``root`` (``rdf:type sast:Query`` plus its own grammar-
    production type, as produced by ``to_ast_rdf.query_ast_to_rdf``) back
    into a real rdflib ``Query`` — reconstructs the ``[prologue, query]``
    parse-tree shape and hands it to rdflib's own, unmodified
    ``translateQuery``."""
    prologue = _decode(graph.value(root, PROLOGUE), graph)
    query = _decode(root, graph)
    return translateQuery([prologue, query])


def _decode(node, graph: Graph) -> Any:
    if node is None:
        return None
    if node == RDF.nil:
        return []

    if isinstance(node, Literal):
        if node.datatype == VARIABLE_DATATYPE:
            return Variable(str(node))
        if node.datatype == PY_STR_DATATYPE:
            return str(node)
        return node

    if isinstance(node, URIRef):
        return node

    if isinstance(node, BNode):
        if (node, RDF.first, None) in graph:
            return [_decode(item, graph) for item in Collection(graph, node)]
        comp_type = _comp_value_type(node, graph)
        if comp_type is not None:
            return _decode_comp_value(node, comp_type, graph)
        return node  # a plain blank node used directly as a query term

    raise NotImplementedError(
        f"starsparql.from_ast_rdf: cannot decode node {node!r} of type {type(node).__name__}"
    )


def _comp_value_type(node, graph: Graph):
    types = [t for t in graph.objects(node, RDF.type) if str(t).startswith(_SAST_NS)]
    if not types:
        return None
    specific = [t for t in types if t not in _AUXILIARY_ROOT_MARKERS]
    return (specific or types)[0]


def _decode_comp_value(node, type_uri, graph: Graph) -> CompValue:
    name = str(type_uri)[len(_SAST_NS):]
    kwargs: dict = {}
    for pred, obj in graph.predicate_objects(node):
        if pred == RDF.type or not str(pred).startswith(_SAST_NS):
            continue
        key = str(pred)[len(_SAST_NS):]
        if key == "prologue":
            # Attached directly to the root node alongside its real
            # grammar-production type (see to_ast_rdf.query_ast_to_rdf) —
            # not one of the CompValue's own keys.
            continue
        kwargs[key] = _decode(obj, graph)

    # Same problem from_rdf.py already solved for the algebra layer: rdflib's
    # evaluator requires expression nodes to be real Expr instances with a
    # bound _evalfn, normally attached only by pyparsing's own grammar
    # actions during a real parse (Comp(name, ...).setEvalFn(fn)) — a bare
    # CompValue reconstructed generically has no such binding. Reuse the
    # exact same discovered {name: evalfn} table (it's introspecting the
    # same live grammar either way), rather than rebuilding it.
    evalfn = _EXPR_EVALFNS.get(name)
    if evalfn is not None:
        result = Expr(name, evalfn)
        result.update(kwargs)
        return result

    return CompValue(name, **kwargs)
