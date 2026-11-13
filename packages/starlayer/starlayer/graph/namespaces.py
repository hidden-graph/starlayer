"""Namespaces and the common vocabularies as pyoxigraph terms: ``RDF.type``, ``XSD.integer``, ``Namespace("http://example.org/").alice``.

pyoxigraph has no namespace helper; this is the one StarLayer code and users share. A name that is not an identifier is
``EX["part-1"]``. Terms are ``pyoxigraph.NamedNode``: StarLayer takes and gives pyoxigraph terms, never rdflib's.
"""

from __future__ import annotations

import pyoxigraph as ox


class Namespace:
    """A namespace of pyoxigraph ``NamedNode`` constants: ``SH.minCount``, ``SH["class"]``. Terms are created once."""

    __slots__ = ("_base", "_cache")

    def __init__(self, base: str) -> None:
        """Create a namespace rooted at the IRI prefix ``base``."""
        object.__setattr__(self, "_base", base)
        object.__setattr__(self, "_cache", {})

    def __getitem__(self, name: str) -> ox.NamedNode:
        """The term for ``name`` in this namespace, built on first use and then reused; use it for names that are not identifiers."""
        node = self._cache.get(name)
        if node is None:
            node = self._cache[name] = ox.NamedNode(self._base + name)
        return node

    def __getattr__(self, name: str) -> ox.NamedNode:
        """Attribute access as ``__getitem__``; dunder names raise ``AttributeError`` so copy and pickle probes do not mint terms."""
        if name.startswith("__"):
            raise AttributeError(name)
        return self[name]

    def term(self, name: str) -> ox.NamedNode:
        """The term for ``name`` (the same as ``ns[name]``)."""
        return self[name]

    def __contains__(self, term: object) -> bool:
        """Whether an IRI (a ``NamedNode`` or its text) is in this namespace: it starts with the base and has a local name."""
        text = term.value if isinstance(term, ox.NamedNode) else term
        return isinstance(text, str) and text.startswith(self._base) and len(text) > len(self._base)

    def __eq__(self, other: object) -> bool:
        """Two namespaces are equal when their base IRIs are."""
        return isinstance(other, Namespace) and other._base == self._base

    def __hash__(self) -> int:
        """Hash by the base IRI."""
        return hash(self._base)

    def __repr__(self) -> str:
        """``Namespace('http://example.org/')``."""
        return f"Namespace({self._base!r})"

    def __str__(self) -> str:
        """The base IRI text, so a namespace can be concatenated into IRI strings."""
        return self._base


RDF = Namespace("http://www.w3.org/1999/02/22-rdf-syntax-ns#")
RDFS = Namespace("http://www.w3.org/2000/01/rdf-schema#")
XSD = Namespace("http://www.w3.org/2001/XMLSchema#")
OWL = Namespace("http://www.w3.org/2002/07/owl#")
SH = Namespace("http://www.w3.org/ns/shacl#")
SHUI = Namespace("http://www.w3.org/ns/shacl-ui/")
SKOS = Namespace("http://www.w3.org/2004/02/skos/core#")
DCTERMS = Namespace("http://purl.org/dc/terms/")
DC = Namespace("http://purl.org/dc/elements/1.1/")
FOAF = Namespace("http://xmlns.com/foaf/0.1/")
PROV = Namespace("http://www.w3.org/ns/prov#")
DCAT = Namespace("http://www.w3.org/ns/dcat#")
PROF = Namespace("http://www.w3.org/ns/dx/prof/")
SCHEMA = Namespace("http://schema.org/")

__all__ = ["DC", "DCAT", "DCTERMS", "FOAF", "OWL", "PROF", "PROV", "RDF", "RDFS", "SCHEMA", "SH", "SHUI", "SKOS", "XSD", "Namespace"]
