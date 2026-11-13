"""pyoxigraph terms for tests: ``lit(5)``, ``NamedNode(iri)``, ``BlankNode()``, ``Namespace(base).name``, plus ``py``/``text`` to read a term back."""

from __future__ import annotations

from decimal import Decimal

import pyoxigraph as ox
from starlayer.graph import OWL, RDF, RDFS, XSD, Namespace
from starlayer.shacl import SH

__all__ = ["list_items", "py", "rdf_list", "set_triple", "text", "DCTERMS", "FOAF", "BlankNode", "NamedNode", "Namespace", "OWL", "RDF", "RDFS", "SH", "SKOS", "XSD", "lit"]

DCTERMS = Namespace("http://purl.org/dc/terms/")
FOAF = Namespace("http://xmlns.com/foaf/0.1/")
SKOS = Namespace("http://www.w3.org/2004/02/skos/core#")

NamedNode = ox.NamedNode
BlankNode = ox.BlankNode


def lit(value, lang=None, datatype=None):
    """A pyoxigraph literal from a Python value: ``str`` plain, ``bool`` xsd:boolean, ``int`` xsd:integer, ``float`` xsd:double, ``Decimal`` xsd:decimal."""
    if lang is not None:
        return ox.Literal(str(value), language=lang)
    if datatype is not None:
        lexical = ("true" if value else "false") if isinstance(value, bool) else str(value)
        return ox.Literal(lexical, datatype=datatype)
    if isinstance(value, bool):
        return ox.Literal("true" if value else "false", datatype=XSD.boolean)
    if isinstance(value, int):
        return ox.Literal(str(value), datatype=XSD.integer)
    if isinstance(value, float):
        return ox.Literal(repr(value), datatype=XSD.double)
    if isinstance(value, Decimal):
        return ox.Literal(str(value), datatype=XSD.decimal)
    return ox.Literal(str(value))


_PY = {
    XSD.integer.value: int,
    XSD.int.value: int,
    XSD.long.value: int,
    XSD.double.value: float,
    XSD.float.value: float,
    XSD.decimal.value: Decimal,
    XSD.boolean.value: lambda lexical: lexical in ("true", "1"),
}


def py(term):
    """The Python value of a literal, as a Python value (the lexical text for types it does not map)."""
    if isinstance(term, ox.Literal):
        convert = _PY.get(term.datatype.value)
        return convert(term.value) if convert else term.value
    return term.value


def text(term):
    """The lexical text of a literal or the IRI text of a named node (``str()`` of a pyoxigraph term adds quotes or angle brackets)."""
    return term.value if isinstance(term, (ox.NamedNode, ox.Literal, ox.BlankNode)) else str(term)


def set_triple(graph, triple):
    """rdflib's ``Graph.set``: replace every value of the triple's subject and predicate with its object."""
    graph.remove((triple[0], triple[1], None))
    graph.add(triple)


def rdf_list(graph, members, head=None):
    """Add an RDF collection of ``members`` to ``graph`` and return its head (``rdf:nil`` when empty); ``head`` names the first cell."""
    members = list(members)
    if not members:
        return RDF.nil
    cells = [head if head is not None else ox.BlankNode()] + [ox.BlankNode() for _ in members[1:]]
    for index, (cell, member) in enumerate(zip(cells, members, strict=True)):
        graph.add((cell, RDF.first, member))
        graph.add((cell, RDF.rest, cells[index + 1] if index + 1 < len(cells) else RDF.nil))
    return cells[0]


def list_items(graph, head):
    """The members of the RDF collection starting at ``head``, in order."""
    items = []
    while head is not None and head != RDF.nil:
        items.append(graph.value(head, RDF.first))
        head = graph.value(head, RDF.rest)
    return items
