"""pyoxigraph terms with rdflib-style spellings for the code KG: ``Literal(5)``, ``URIRef(iri)``, ``Namespace(base).name``.

StarLayer takes pyoxigraph terms; the extractor and the queries build and read them through these names.
"""

from __future__ import annotations

from decimal import Decimal

import pyoxigraph as ox


class Namespace:
    """Vocabulary terms as pyoxigraph ``NamedNode`` constants (``RDF.type``, ``NS["a-b"]``); a small copy of
    ``starlayer.graph.Namespace`` so that importing the code KG does not import starlayer (see ``codekg/__init__``)."""

    def __init__(self, base: str) -> None:
        self._base = base

    def __getitem__(self, name: str) -> ox.NamedNode:
        return ox.NamedNode(self._base + name)

    def __getattr__(self, name: str) -> ox.NamedNode:
        if name.startswith("_"):
            raise AttributeError(name)
        return self[name]

    def __str__(self) -> str:
        return self._base


RDF = Namespace("http://www.w3.org/1999/02/22-rdf-syntax-ns#")
RDFS = Namespace("http://www.w3.org/2000/01/rdf-schema#")
XSD = Namespace("http://www.w3.org/2001/XMLSchema#")
DCTERMS = Namespace("http://purl.org/dc/terms/")

URIRef = ox.NamedNode

__all__ = ["DCTERMS", "RDF", "RDFS", "XSD", "Literal", "Namespace", "URIRef", "text"]


def Literal(value, lang=None, datatype=None):  # noqa: N802 - mirrors rdflib's constructor name
    """A pyoxigraph literal from a Python value, typed as rdflib typed it (``bool`` before ``int``)."""
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


def text(term) -> str:
    """The lexical text of a literal or the IRI of a named node (``str()`` of a pyoxigraph term adds quotes or angle brackets)."""
    return term.value if isinstance(term, (ox.NamedNode, ox.Literal, ox.BlankNode)) else str(term)
