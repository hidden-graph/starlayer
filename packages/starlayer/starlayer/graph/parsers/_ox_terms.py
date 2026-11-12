"""pyoxigraph terms for the Manchester syntax reader and writer (``manchester_parser``, ``serializers/manchester``,
``starontology/manchester``): the term classes, the OWL / RDF / RDFS / XSD vocabularies as ``NamedNode`` attributes, and the
few constructors whose pyoxigraph signature differs from rdflib's. No rdflib import."""

from __future__ import annotations

import re

import pyoxigraph as ox

URIRef = ox.NamedNode
BNode = ox.BlankNode
Literal = ox.Literal


class Vocab:
    """``Vocab("http://...#").Name`` and ``["Name"]`` are the ``NamedNode`` of the namespace IRI plus the name; ``str(vocab)``
    is the namespace IRI."""

    __slots__ = ("_base", "_cache")

    def __init__(self, base: str) -> None:
        """A vocabulary over the namespace IRI ``base``."""
        self._base = base
        self._cache: dict[str, ox.NamedNode] = {}

    def __getitem__(self, name: str) -> ox.NamedNode:
        """The ``NamedNode`` of the namespace IRI plus ``name``; one node is made per name and reused."""
        node = self._cache.get(name)
        if node is None:
            node = self._cache[name] = ox.NamedNode(self._base + name)
        return node

    def __getattr__(self, name: str) -> ox.NamedNode:
        """Attribute access as ``self[name]``; names starting with ``__`` raise ``AttributeError`` instead."""
        if name.startswith("__"):
            raise AttributeError(name)
        return self[name]

    def __str__(self) -> str:
        """The namespace IRI."""
        return self._base

    def __contains__(self, node: object) -> bool:
        """Whether ``node`` is a ``NamedNode`` whose IRI starts with the namespace IRI."""
        return isinstance(node, ox.NamedNode) and node.value.startswith(self._base)


OWL = Vocab("http://www.w3.org/2002/07/owl#")
RDF = Vocab("http://www.w3.org/1999/02/22-rdf-syntax-ns#")
RDFS = Vocab("http://www.w3.org/2000/01/rdf-schema#")
XSD = Vocab("http://www.w3.org/2001/XMLSchema#")

_LANGTAG = re.compile(r"^[a-zA-Z]+(?:-[a-zA-Z0-9]+)*$")


def is_valid_langtag(tag: str) -> bool:
    """The language-tag shape the Manchester note's ``languageTag`` allows (a letter run, then ``-`` runs)."""
    return bool(_LANGTAG.match(tag))


def lexical(value: bool | int | str, datatype: ox.NamedNode | None = None, lang: str | None = None) -> ox.Literal:
    """A literal from a Python value: ``True`` is ``"true"^^xsd:boolean``, an ``int`` is ``xsd:integer`` unless ``datatype``
    is given, a ``str`` is a plain (or ``datatype`` / ``lang``) literal. The lexical form is kept as given."""
    if isinstance(value, bool):
        return ox.Literal("true" if value else "false", datatype=XSD.boolean)
    if isinstance(value, int):
        return ox.Literal(str(value), datatype=datatype or XSD.integer)
    if lang:
        return ox.Literal(value, language=lang)
    if datatype is not None:
        return ox.Literal(value, datatype=datatype)
    return ox.Literal(value)
