"""StarLayer graphs: RDF 1.2 graphs and datasets over Oxigraph.

``StarLayerGraph`` (one graph) and ``StarLayerDataset`` (a store of named graphs) are composition wrappers over a
``pyoxigraph.Store``; terms are pyoxigraph terms. Parsing, serialization, SPARQL 1.2 query and update, and RDFC-1.0
canonicalisation run on Oxigraph. ``from_rdflib`` / ``to_rdflib`` convert to and from rdflib, which is an optional extra.
Entailment regimes are the W3C IRIs in ``ENTAILMENT``.
"""

from starlayer.graph.compare import isomorphic
from starlayer.graph.model.dirlangstring import DirLangString
from starlayer.graph.model.triple import TripleTerm
from starlayer.graph.oxgraph.core import StarLayerDataset, StarLayerGraph
from starlayer.graph.oxgraph.endpoint import Endpoint, EndpointError
from starlayer.graph.oxgraph.helpers.entailment import ENTAILMENT
from starlayer.graph.oxgraph.helpers.imports import can_resolve_import

__all__ = [
    "ENTAILMENT",
    "DirLangString",
    "Endpoint",
    "EndpointError",
    "StarLayerDataset",
    "StarLayerGraph",
    "TripleTerm",
    "can_resolve_import",
    "isomorphic",
]
