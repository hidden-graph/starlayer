"""StarLayer graphs: RDF 1.2 graphs and datasets over Oxigraph.

``StarLayerGraph`` (one graph) and ``StarLayerDataset`` (a store of named graphs) are composition wrappers over a
``pyoxigraph.Store``; terms are pyoxigraph terms. Parsing, serialization, SPARQL 1.2 query and update, and RDFC-1.0
canonicalisation run on Oxigraph. ``from_rdflib`` / ``to_rdflib`` convert to and from rdflib, which is an optional extra.
Entailment regimes are the W3C IRIs in ``ENTAILMENT``.
"""

from starlayer.graph import config, reification
from starlayer.graph.compare import isomorphic
from starlayer.graph.config import DEFAULT_PREFIXES, set_default_prefixes
from starlayer.graph.core import StarLayerDataset, StarLayerGraph, as_store
from starlayer.graph.endpoint import Endpoint, EndpointError
from starlayer.graph.entailment import ENTAILMENT
from starlayer.graph.execution.result import Result, Row
from starlayer.graph.execution.session import EntailmentSession
from starlayer.graph.imports import can_resolve_import
from starlayer.graph.namespaces import OWL, RDF, RDFS, XSD, Namespace

__all__ = [
    "DEFAULT_PREFIXES",
    "ENTAILMENT",
    "Endpoint",
    "EndpointError",
    "EntailmentSession",
    "Namespace",
    "OWL",
    "RDF",
    "RDFS",
    "Result",
    "Row",
    "XSD",
    "StarLayerDataset",
    "StarLayerGraph",
    "as_store",
    "can_resolve_import",
    "config",
    "isomorphic",
    "reification",
    "set_default_prefixes",
]
