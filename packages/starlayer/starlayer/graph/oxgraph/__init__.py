"""Oxigraph-backed graph wrapper (working names ``OxGraph`` / ``OxDataset``, to become ``StarLayerGraph`` /
``StarLayerDataset`` at the switch). See docs/working/oxgraph-wrapper.md."""

from starlayer.graph.oxgraph import config, reification
from starlayer.graph.oxgraph.config import DEFAULT_PREFIXES, set_default_prefixes
from starlayer.graph.oxgraph.core import OxDataset, OxGraph, as_store
from starlayer.graph.oxgraph.result import Result, Row

__all__ = ["DEFAULT_PREFIXES", "OxDataset", "OxGraph", "Result", "Row", "as_store", "config", "reification", "set_default_prefixes"]
