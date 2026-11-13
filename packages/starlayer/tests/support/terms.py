"""pyoxigraph terms for tests: ``lit(5)``, ``NamedNode(iri)``, ``BlankNode()``, ``Namespace(base).name``, plus ``py``/``text`` to read a term back."""

from __future__ import annotations

import pyoxigraph as ox
from starlayer.graph import (
    DCTERMS,
    FOAF,
    OWL,
    RDF,
    RDFS,
    SKOS,
    XSD,
    Namespace,
    literal,
    to_python,
)
from starlayer.shacl import SH

__all__ = ["list_items", "py", "rdf_list", "set_triple", "text", "DCTERMS", "FOAF", "BlankNode", "NamedNode", "Namespace", "OWL", "RDF", "RDFS", "SH", "SKOS", "XSD", "lit"]

NamedNode = ox.NamedNode
BlankNode = ox.BlankNode


def lit(value, lang=None, datatype=None):
    """A pyoxigraph literal from a Python value (``starlayer.graph.literal``): ``str`` plain, ``bool`` xsd:boolean, ``int`` xsd:integer, ``float`` xsd:double, ``Decimal`` xsd:decimal."""
    return literal(value, datatype, lang=lang)


def py(term):
    """The Python value of a literal (``starlayer.graph.to_python``; the lexical text when the lexical form is not valid for its datatype); the text of any other term."""
    if isinstance(term, ox.Literal):
        try:
            return to_python(term)
        except ValueError:
            return term.value
    return term.value


def text(term):
    """The lexical text of a literal or the IRI text of a named node (``str()`` of a pyoxigraph term adds quotes or angle brackets)."""
    return term.value if isinstance(term, (ox.NamedNode, ox.Literal, ox.BlankNode)) else str(term)


def set_triple(graph, triple):
    """rdflib's ``Graph.set``: replace every value of the triple's subject and predicate with its object."""
    graph.set(triple)


def rdf_list(graph, members, head=None):
    """Add an RDF collection of ``members`` to ``graph`` and return its head (``rdf:nil`` when empty); ``head`` names the first cell."""
    return graph.add_list(members, head)


def list_items(graph, head):
    """The members of the RDF collection starting at ``head``, in order."""
    return list(graph.items(head))
