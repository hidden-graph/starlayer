"""The Oxigraph-backed graph classes ``StarLayerGraph`` / ``StarLayerDataset`` and their helpers; ``starlayer.graph`` re-exports the
two classes. See docs/working/oxgraph-wrapper.md."""

from starlayer.graph.oxgraph import config, reification
from starlayer.graph.oxgraph.config import DEFAULT_PREFIXES, set_default_prefixes
from starlayer.graph.oxgraph.core import StarLayerDataset, StarLayerGraph, as_store
from starlayer.graph.oxgraph.result import Result, Row
from starlayer.graph.oxgraph.session import EntailmentSession

__all__ = ["DEFAULT_PREFIXES", "EntailmentSession", "StarLayerDataset", "StarLayerGraph", "Result", "Row", "as_store", "config", "reification", "set_default_prefixes"]
