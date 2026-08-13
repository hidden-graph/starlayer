"""Encode a bare SELECT query's raw parse tree (``parseQuery()`` output,
same input ``to_ast_rdf.query_ast_to_rdf`` takes) as ``ssyn:`` — the
*readable* syntax-level RDF, no more verbose than the query text itself.

Everything that collapses the parse tree's native verbosity is a real,
existing rdflib function, reused directly, never reimplemented:

- ``algebra.translatePName`` (via ``traverse(..., visitPost=...)``) resolves
  prefixed names (``foaf:Person``) to real absolute IRIs — the parse tree
  keeps them as unresolved ``prefix``/``localname`` pairs otherwise.
- ``algebra.triples`` groups a ``TriplesBlock``'s flat, ungrouped run of
  terms into real ``(s, p, o)`` tuples (also reordering them — harmless
  here since a plain BGP's own triple order isn't semantically meaningful).
- ``algebra.translatePath`` collapses a trivial single-element
  ``PathAlternative``/``PathSequence``/``PathElt`` chain down to the bare
  predicate term, or builds a real ``rdflib.paths.Path`` object for a
  genuine path — reusing ``to_rdf._encode_path`` (unchanged) for the latter,
  the same salg:-boundary principle as expressions below.
- ``algebra.simplifyFilters`` collapses a ``ConditionalOrExpression ->
  ConditionalAndExpression -> ...`` precedence chain down to whatever real
  expression is actually present, whenever there's no genuine ``&&``/``||``.

A ``WHERE`` clause is encoded as a flat, ordered list of sibling elements —
mirroring ``GroupGraphPatternSub.part``'s own already-flat shape in the raw
parse tree — not the algebra's nested ``LeftJoin``/``Filter`` wrapping. See
``ssyn_vocab.py``'s module docstring for why.
"""

from __future__ import annotations

import functools
from typing import Optional, Union

from rdflib import BNode, Graph, Literal, URIRef, Variable
from rdflib.collection import Collection
from rdflib.namespace import RDF
from rdflib.paths import Path
from rdflib.plugins.sparql.algebra import (
    simplifyFilters,
    translatePath,
    translatePName,
    translatePrologue,
    traverse,
)
from rdflib.plugins.sparql.algebra import triples as group_triples
from rdflib.plugins.sparql.parserutils import CompValue, ParseResults

from .ssyn_vocab import (
    BIND,
    BIND_VAR,
    EXPR,
    FILTER,
    OPTIONAL,
    SELECT,
    SELECT_QUERY,
    SSYN,
    TRIPLE_PATTERN,
    TRIPLE_PATTERN_OBJECT,
    TRIPLE_PATTERN_PREDICATE,
    TRIPLE_PATTERN_SUBJECT,
    UNION,
    UNION_ALTERNATIVES,
    VARIABLE_DATATYPE,
    WHERE,
)
from .to_rdf import _encode as _encode_algebra
from .to_rdf import _encode_path, _new_starlayer_graph


def query_to_ssyn_rdf(parse_result: ParseResults, graph: Optional[Graph] = None) -> tuple[Graph, BNode]:
    """Encode a bare ``SELECT`` query's raw parse tree
    (``parseQuery(text)``'s output — ``[prologue, query]``) as ``ssyn:``
    RDF. Returns ``(graph, root)``.

    Raises ``NotImplementedError`` for anything outside this slice's scope
    (non-``SELECT`` forms, ``DISTINCT``/``LIMIT``/``ORDER BY``/subqueries/
    ``MINUS``/``SERVICE`` inside ``WHERE``) rather than silently
    mis-encoding — same discipline as every other scope boundary in this
    project. ``graph`` defaults to a fresh ``StarLayerGraph`` (see
    ``to_rdf._new_starlayer_graph``), never a plain ``rdflib.Graph``.
    """
    prologue_list, query = parse_result[0], parse_result[1]
    if query.name != "SelectQuery":
        raise NotImplementedError(
            f"starsparql.to_ssyn_rdf: only bare SelectQuery is modeled yet, got {query.name!r}"
        )

    # Reuse rdflib's own prefix-resolution pass unchanged — same call
    # translateQuery itself makes, just without the rest of that function.
    prologue = translatePrologue(prologue_list, base=None)
    query = traverse(query, visitPost=functools.partial(translatePName, prologue=prologue))

    # Same ordering translate() itself uses (q.where = traverse(q.where,
    # visitPost=translatePath)), and for the same reason: algebra.triples()
    # (called below, per TriplesBlock) runs reorderTriples, which needs
    # every term — including the predicate position — to already be
    # hashable. A raw PathAlternative/PathSequence/PathElt CompValue isn't;
    # translatePath must run first, not per-predicate after grouping (confirmed
    # by hitting the exact "cannot use CompValue as a set element" crash
    # CLAUDE.md finding #11 describes, doing it the other order first).
    query.where = traverse(query.where, visitPost=translatePath)

    if graph is None:
        graph = _new_starlayer_graph()
    root = BNode()
    graph.add((root, RDF.type, SELECT_QUERY))
    graph.add((root, SELECT, _encode_var_list(query.projection, graph)))
    graph.add((root, WHERE, _encode_where_group(query.where, graph)))
    return graph, root


def _encode_var_list(projection, graph: Graph):
    variables = [v.var for v in projection]
    return _build_rdf_list([_encode_variable(v) for v in variables], graph)


def _encode_where_group(group: CompValue, graph: Graph):
    """``GroupGraphPatternSub`` -> a flat, ordered rdf:List of sibling
    pattern elements — its ``.part`` is already exactly this shape in the
    raw parse tree, just walked here instead of copied as-is, since each
    element still needs its own contents simplified/encoded.

    A ``TriplesBlock`` sibling splices in *multiple* nodes (one per real
    triple, via ``algebra.triples``' own grouping) rather than one wrapper
    node — each triple reads more naturally as its own flat sibling than as
    a member of a BGP-shaped sub-list, matching this layer's "no more
    verbose than the text" goal.
    """
    nodes: list = []
    for part in group.part or []:
        if part.name == "TriplesBlock":
            for s, p, o in group_triples(part.triples):
                nodes.append(_encode_triple_pattern(s, p, o, graph))
        else:
            nodes.append(_encode_where_element(part, graph))
    return _build_rdf_list(nodes, graph)


def _encode_where_element(part: CompValue, graph: Graph) -> BNode:
    if part.name == "OptionalGraphPattern":
        node = BNode()
        graph.add((node, RDF.type, OPTIONAL))
        graph.add((node, WHERE, _encode_where_group(part.graph, graph)))
        return node
    if part.name == "Filter":
        node = BNode()
        graph.add((node, RDF.type, FILTER))
        graph.add((node, EXPR, _encode_algebra(simplifyFilters(part.expr), graph)))
        return node
    if part.name == "Bind":
        node = BNode()
        graph.add((node, RDF.type, BIND))
        graph.add((node, EXPR, _encode_algebra(simplifyFilters(part.expr), graph)))
        graph.add((node, BIND_VAR, _encode_variable(part.var)))
        return node
    if part.name == "GroupOrUnionGraphPattern":
        node = BNode()
        graph.add((node, RDF.type, UNION))
        alts = _build_rdf_list([_encode_where_group(alt, graph) for alt in part.graph], graph)
        graph.add((node, UNION_ALTERNATIVES, alts))
        return node
    raise NotImplementedError(
        f"starsparql.to_ssyn_rdf: WHERE-clause element {part.name!r} not modeled yet"
    )


def _encode_triple_pattern(s, p, o, graph: Graph) -> BNode:
    node = BNode()
    graph.add((node, RDF.type, TRIPLE_PATTERN))
    graph.add((node, TRIPLE_PATTERN_SUBJECT, _encode_term(s, graph)))
    graph.add((node, TRIPLE_PATTERN_PREDICATE, _encode_predicate(p, graph)))
    graph.add((node, TRIPLE_PATTERN_OBJECT, _encode_term(o, graph)))
    return node


def _encode_predicate(p, graph: Graph):
    """A predicate position may be a genuine property path — collapse the
    trivial (non-path) case down to a bare term via rdflib's own
    translatePath, and fall back to the existing salg: path encoding
    (to_rdf._encode_path, unchanged) only for a real path."""
    translated = translatePath(p) if isinstance(p, CompValue) else p
    if isinstance(translated, Path):
        return _encode_path(translated, graph)
    return _encode_term(translated, graph)


def _encode_term(value, graph: Graph):
    if isinstance(value, Variable):
        return _encode_variable(value)
    return value  # a real, already-resolved RDF term (URIRef/BNode/Literal)


def _encode_variable(value: Variable) -> Literal:
    return Literal(str(value), datatype=VARIABLE_DATATYPE)


def _build_rdf_list(nodes: list, graph: Graph) -> Union[BNode, URIRef]:
    if not nodes:
        return RDF.nil
    list_node = BNode()
    Collection(graph, list_node, nodes)
    return list_node
