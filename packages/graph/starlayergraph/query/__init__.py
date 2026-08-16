"""Query utilities for translating RDF 1.2/SPARQL-star syntax.

This package is intentionally separate from ``starlayergraph.graph`` so query
translation can be developed and tested without changing ``StarLayerGraph``.
"""

from rdflib.plugins.sparql.parserutils import CompValue

from .sparql_api import (
    parseQuery,
    parseUpdate,
    prepareQuery,
    prepareUpdate,
    processUpdate,
)

__all__ = [
    "parseQuery",
    "prepareQuery",
    "parseUpdate",
    "prepareUpdate",
    "processUpdate",
    "CompValue",
]