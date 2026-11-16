"""StarLayer graphs: RDF 1.2 graphs and datasets over Oxigraph.

``StarLayerGraph`` (one graph) and ``StarLayerDataset`` (a store of named graphs) are composition wrappers over a
``pyoxigraph.Store``; terms are pyoxigraph terms. Parsing, serialization, SPARQL 1.2 query and update, and RDFC-1.0
canonicalisation run on Oxigraph. ``from_rdflib`` / ``to_rdflib`` convert to and from rdflib and need rdflib (``pip install "starlayer[rdflib]"``).
Entailment regimes are the W3C IRIs in ``ENTAILMENT``. ``NamedNode``, ``BlankNode``, ``Literal``, ``Triple`` and ``BaseDirection`` are
pyoxigraph's own classes, re-exported so that a program needs one import for them and the graph.
"""

from pyoxigraph import BaseDirection, BlankNode, Literal, NamedNode, Triple

from starlayer.graph import config, reification
from starlayer.graph.bnode_align import Alignment, BlankNodePair, align_blank_nodes
from starlayer.graph.compare import isomorphic
from starlayer.graph.config import DEFAULT_PREFIXES, set_default_prefixes
from starlayer.graph.core import StarLayerDataset, StarLayerGraph, as_store
from starlayer.graph.delta import GraphDelta, diff
from starlayer.graph.endpoint import Endpoint, EndpointError
from starlayer.graph.entailment import ENTAILMENT
from starlayer.graph.execution.result import Result, Row
from starlayer.graph.execution.session import EntailmentSession
from starlayer.graph.imports import can_resolve_import
from starlayer.graph.namespaces import (
    DCAT,
    DCTERMS,
    FOAF,
    OWL,
    PROV,
    RDF,
    RDFS,
    SCHEMA,
    SKOS,
    XSD,
    Namespace,
)
from starlayer.graph.profile import GraphProfile, PropertyUse, profile
from starlayer.graph.terms import literal, parse_term, to_python

__all__ = [
    "Alignment",
    "BaseDirection",
    "BlankNode",
    "BlankNodePair",
    "DCAT",
    "DCTERMS",
    "DEFAULT_PREFIXES",
    "ENTAILMENT",
    "Endpoint",
    "EndpointError",
    "EntailmentSession",
    "FOAF",
    "Literal",
    "Namespace",
    "NamedNode",
    "OWL",
    "PROV",
    "RDF",
    "RDFS",
    "Result",
    "Row",
    "SCHEMA",
    "SKOS",
    "Triple",
    "XSD",
    "StarLayerDataset",
    "GraphDelta",
    "GraphProfile",
    "PropertyUse",
    "StarLayerGraph",
    "align_blank_nodes",
    "as_store",
    "can_resolve_import",
    "config",
    "diff",
    "isomorphic",
    "literal",
    "parse_term",
    "profile",
    "reification",
    "set_default_prefixes",
    "to_python",
]
