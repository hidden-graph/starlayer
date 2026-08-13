"""Query utilities for translating RDF 1.2/SPARQL-star syntax.

This package is intentionally separate from ``starlayergraph.graph`` so query
translation can be developed and tested without changing ``StarLayerGraph``.
"""

from .sparql_api import parseQuery, prepareQuery, parseUpdate, prepareUpdate, processUpdate
from rdflib.plugins.sparql.parserutils import CompValue

__all__ = [
    "parseQuery",
    "prepareQuery",
    "parseUpdate",
    "prepareUpdate",
    "processUpdate",
    "CompValue",
]