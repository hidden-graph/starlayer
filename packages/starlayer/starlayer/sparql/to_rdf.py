"""Encode a SPARQL algebra tree (rdflib CompValue/Expr nodes) as RDF triples.

One generic recursive walker handles every algebra operator and every
expression builtin uniformly — see ``vocab.py``'s module docstring for why
that is the design (and not one function per operator name).
"""

from __future__ import annotations

import starlayer._needs_rdflib  # noqa: F401  (a clear ImportError when rdflib is not installed)

# isort: split
from rdflib import BNode, Graph, URIRef
from rdflib.namespace import RDF
from rdflib.plugins.sparql.sparql import Prologue, Query, Update

from .spexpr_codec import _build_rdf_list, _encode, _new_tree_graph
from .vocab import (
    QUERY,
    QUERY_COLLECTION,
    SALG,
    UPDATE,
    UPDATE_OPERATION,
)


def query_to_rdf(query: Query, graph: Graph | None = None) -> tuple[Graph, BNode]:
    """Encode a prepared rdflib ``Query`` (from ``prepareQuery``/``translateQuery``,
    starlayer.graph's SPARQL-1.2-aware variants included) as RDF triples.

    ``root`` is the node for ``query.algebra``, additionally typed
    ``salg:Query`` (see ``vocab.QUERY``) so encoded queries in a larger
    store can always be found via ``?q a salg:Query`` regardless of query
    form.

    Args:
        query: The prepared query to encode.
        graph: The graph to add the encoding triples to; a fresh
            plain ``rdflib.Graph`` (see ``_new_tree_graph``) if omitted.

    Returns:
        ``(graph, root)``.
    """
    if getattr(query, "algebra", None) is None:
        raise TypeError(f"query must be a prepared rdflib Query (see prepareQuery), not {type(query).__name__}")
    from starlayer.graph.oxgraph import _rdflib_bridge as _ox

    if graph is not None and _ox.is_oxigraph_input(graph):  # an StarLayerGraph target: encode on rdflib terms, then add them to it
        return _ox.write_boundary(graph, lambda g: query_to_rdf(query, g))
    if graph is None:
        graph = _new_tree_graph()
    root = _encode(query.algebra, graph)
    graph.add((root, RDF.type, QUERY))
    _encode_prologue(query.prologue, root, graph)
    return graph, root


def update_to_rdf(update: Update, graph: Graph | None = None) -> tuple[Graph, BNode]:
    """Encode a prepared rdflib ``Update`` (from ``prepareUpdate``/
    ``translateUpdate``) as RDF triples.

    ``update.algebra`` is a ``List[CompValue]`` — one operation per
    semicolon-separated request in the Update string, executed in that
    order. ``root`` is a dedicated container node (not itself a CompValue,
    typed ``salg:Update`` — see ``vocab.UPDATE``) holding ``salg:operations``
    (an ``rdf:List`` of the encoded operations — order matters and must
    survive the round-trip) plus the request's shared Prologue
    (``salg:base``/``salg:prologuePrefix`` — SPARQL Update has one Prologue
    per request, not one per operation, unlike a Query). Each operation node
    is additionally typed ``salg:UpdateOperation`` (see
    ``vocab.UPDATE_OPERATION``).

    Args:
        update: The prepared update to encode.
        graph: The graph to add the encoding triples to; a fresh
            plain ``rdflib.Graph`` (see ``_new_tree_graph``) if omitted.

    Returns:
        ``(graph, root)``.
    """
    if getattr(update, "algebra", None) is None:
        raise TypeError(f"update must be a prepared rdflib Update (see prepareUpdate), not {type(update).__name__}")
    from starlayer.graph.oxgraph import _rdflib_bridge as _ox

    if graph is not None and _ox.is_oxigraph_input(graph):  # an StarLayerGraph target: encode on rdflib terms, then add them to it
        return _ox.write_boundary(graph, lambda g: update_to_rdf(update, g))
    if graph is None:
        graph = _new_tree_graph()
    op_nodes = []
    for op in update.algebra:
        node = _encode(op, graph)
        graph.add((node, RDF.type, UPDATE_OPERATION))
        op_nodes.append(node)
    root = BNode()
    graph.add((root, RDF.type, UPDATE))
    graph.add((root, SALG.operations, _build_rdf_list(op_nodes, graph)))
    _encode_prologue(update.prologue, root, graph)
    return graph, root


def queries_to_collection(queries: list[Query], graph: Graph | None = None) -> tuple[Graph, BNode]:
    """Encodes a list of independent, prepared rdflib ``Query`` objects as
    one RDF ``salg:QueryCollection``.

    The collection-of-independent-queries counterpart of
    ``update_to_rdf``'s single-request ``salg:operations`` list - see
    ``vocab.QUERY_COLLECTION``. Unlike an Update's operations, which
    share one Prologue across the whole request, each query keeps its
    own — ``query_to_rdf`` already encodes it per query, so nothing extra
    is needed here for that.

    Args:
        queries: The independent queries to encode.
        graph: The graph to add the encoding triples to; a fresh
            plain ``rdflib.Graph`` (see ``_new_tree_graph``) if omitted.

    Returns:
        ``(graph, root)`` — ``root`` is a dedicated container node holding
        ``salg:queries`` (an ``rdf:List`` of the member queries' own
        ``salg:Query``-typed roots, in the order given — order isn't
        semantically meaningful for a collection, but is preserved anyway
        since ``rdf:List`` is ordered regardless).
    """
    if isinstance(queries, (str, bytes)) or not hasattr(queries, "__iter__"):
        raise TypeError(f"queries must be a list of prepared Query objects, not {type(queries).__name__}")
    if graph is None:
        graph = _new_tree_graph()
    query_nodes = [query_to_rdf(query, graph)[1] for query in queries]
    root = BNode()
    graph.add((root, RDF.type, QUERY_COLLECTION))
    graph.add((root, SALG.queries, _build_rdf_list(query_nodes, graph)))
    return graph, root


def _encode_prologue(prologue: Prologue | None, root: BNode, graph: Graph) -> None:
    """Encode a Query/Update's Prologue (BASE + PREFIX declarations) onto its
    root node.

    See vocab.py's "Prologue (BASE/PREFIX)" section for why this is
    round-tripped (BASE-relative IRI()/URI() builtin correctness) and what
    it doesn't fix (rdflib's own algebra.translateAlgebra never reads
    prologue, so this can't make regenerated query text use prefixes).

    Args:
        prologue: The Query/Update's Prologue, or ``None`` to skip encoding.
        root: The query/update root node to attach the prologue to.
        graph: The graph to add the encoding triples to.
    """
    if prologue is None:
        return
    if prologue.base:
        graph.add((root, SALG.base, URIRef(prologue.base)))
    for prefix, namespace in prologue.namespace_manager.namespaces():
        binding = BNode()
        graph.add((binding, RDF.type, SALG.PrefixBinding))
        graph.add((binding, SALG.prefixLabel, _encode(prefix, graph)))
        graph.add((binding, SALG.namespace, URIRef(namespace)))
        graph.add((root, SALG.prologuePrefix, binding))


