"""BRIDGE to rdflib. The only place in the Oxigraph wrapper that converts to and from rdflib terms.

Some capabilities still run on rdflib-based code that has no Oxigraph equivalent: ``owlrl`` (RDFS / OWL-RL closure), the OWL-DL
bridges (HermiT via owlready2, rustdl) and ``derive_shape``. They take a copy of the graph as rdflib terms, run, and the delta is
converted back to pyoxigraph terms. When one of them gets a native port, delete its use of this module; when the last one goes,
delete the module.

Everything here imports rdflib lazily, so ``import starlayer.graph.oxgraph`` stays free of it.
"""

from __future__ import annotations

from collections.abc import Iterable, Iterator
from typing import Any

import pyoxigraph as ox


def to_rdflib_term(term: Any) -> Any:
    """pyoxigraph term -> rdflib / StarLayer term (a triple term becomes a ``TripleTerm``)."""
    from starlayer.shacl_engine.terms import from_engine

    return from_engine(term)


def to_rdflib_triples(triples: Iterable[tuple[Any, Any, Any]]) -> list[tuple[Any, Any, Any]]:
    from starlayer.shacl_engine.terms import from_engine

    return [(from_engine(s), from_engine(p), from_engine(o)) for s, p, o in triples]


def rdflib_graph(triples: Iterable[tuple[Any, Any, Any]], *, decompose: bool = True) -> Any:
    """A plain ``rdflib.Graph`` with the triples. ``decompose=True`` replaces every triple term with a synthetic reification
    fragment (what the reasoners need; they cannot hold a triple term), as ``starlayer.graph.compare._decompose`` does."""
    from rdflib import Graph

    rows = to_rdflib_triples(triples)
    out = Graph()
    if decompose:
        from starlayer.graph.compare import _decompose_quads

        for s, p, o, _g in _decompose_quads((s, p, o, None) for s, p, o in rows):
            out.add((s, p, o))
    else:
        for t in rows:
            out.add(t)
    return out


def starlayer_graph(triples: Iterable[tuple[Any, Any, Any]], prefixes: dict[str, str] | None = None) -> Any:
    """An old-style ``StarLayerGraph`` (keeps triple terms) holding the triples; used where the code to run needs RDF 1.2."""
    from starlayer.graph.graph.starlayer_graph import StarLayerGraph

    g = StarLayerGraph()
    for prefix, ns in (prefixes or {}).items():
        g.bind(prefix, ns)
    for t in to_rdflib_triples(triples):
        g.add(t)
    return g


def _decode_dirlang(term: Any) -> Any:
    from starlayer.graph.model.encoding import decode_dirlang_datatype

    dt = getattr(term, "datatype", None)
    decoded = decode_dirlang_datatype(dt) if dt is not None else None
    if decoded is None:
        return None
    lang, direction = decoded
    return ox.Literal(str(term), language=lang, direction=ox.BaseDirection.RTL if direction == "rtl" else ox.BaseDirection.LTR)


def from_rdflib_term(term: Any) -> Any:
    """rdflib / StarLayer term -> pyoxigraph term (a decomposed directional-language encoding is restored)."""
    from rdflib import Literal as RLiteral

    from starlayer.shacl_engine.terms import to_engine

    if isinstance(term, RLiteral):
        restored = _decode_dirlang(term)
        if restored is not None:
            return restored
    return to_engine(term)


def legal_rdf_triples(triples: Iterable[tuple[Any, Any, Any]]) -> Iterator[tuple[Any, Any, Any]]:
    """The rdflib triples of ``triples`` that RDF allows, as pyoxigraph triples. OWL RL and RDFS also derive generalized triples
    such as ``"text" rdf:type rdfs:Literal`` (literal subject, or a non-IRI predicate), which no RDF store holds."""
    from rdflib import Literal as RLiteral
    from rdflib import URIRef

    for s, p, o in triples:
        if isinstance(s, RLiteral) or not isinstance(p, URIRef):
            continue
        yield from_rdflib_term(s), from_rdflib_term(p), from_rdflib_term(o)
