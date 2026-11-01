"""Term coercion for the wrapper. Terms are pyoxigraph terms; an rdflib or StarLayer term is converted (rdflib is imported
lazily, only when such a term actually arrives)."""

from __future__ import annotations

from typing import Any

import pyoxigraph as ox

NamedNode, BlankNode, Literal, Triple, Variable = ox.NamedNode, ox.BlankNode, ox.Literal, ox.Triple, ox.Variable
DefaultGraph = ox.DefaultGraph

RDF = "http://www.w3.org/1999/02/22-rdf-syntax-ns#"
RDF_TYPE = NamedNode(RDF + "type")
RDF_VALUE = NamedNode(RDF + "value")
RDF_FIRST = NamedNode(RDF + "first")
RDF_REST = NamedNode(RDF + "rest")
RDF_NIL = NamedNode(RDF + "nil")
RDF_REIFIES = NamedNode(RDF + "reifies")

_OX_TERMS = (ox.NamedNode, ox.BlankNode, ox.Literal, ox.Triple)


def term(x: Any) -> Any:
    """``x`` as a pyoxigraph term (``None`` stays ``None``; a 3-tuple becomes a ``Triple``)."""
    if x is None or isinstance(x, _OX_TERMS):
        return x
    if isinstance(x, tuple) and len(x) == 3:
        return Triple(term(x[0]), term(x[1]), term(x[2]))
    from starlayer.shacl_engine.terms import (
        to_engine,  # rdflib / StarLayer terms; imports rdflib lazily
    )

    return to_engine(x)


def graph_name(x: Any) -> Any:
    """A graph identifier as ``NamedNode`` / ``BlankNode`` / ``DefaultGraph``. A plain ``str`` is an IRI."""
    if x is None or isinstance(x, ox.DefaultGraph):
        return ox.DefaultGraph()
    if isinstance(x, str):
        return NamedNode(x)
    ident = getattr(x, "identifier", None)  # an OxGraph
    if ident is not None:
        return ident
    return term(x)


def in_pattern(s: Any, p: Any, o: Any) -> tuple[Any, Any, Any] | None:
    """Pattern terms coerced; ``None`` when no RDF statement can match (a literal subject or a non-IRI predicate), because
    Oxigraph raises there while an RDF graph simply has no such statement."""
    s, p, o = term(s), term(p), term(o)
    if isinstance(s, (ox.Literal, ox.Triple)) or (p is not None and not isinstance(p, ox.NamedNode)):
        return None
    return s, p, o
