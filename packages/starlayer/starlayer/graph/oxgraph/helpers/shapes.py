"""``derive_shape``: infer a SHACL shapes graph from the data of an ``OxGraph`` / ``OxDataset``.

Stage 1 port: the derivation (``graph/graph/shape_derivation.py``, rdflib terms, self-checks through ``starlayer.shacl``) is
reused unchanged. The data (and a template shape, if it is a wrapper) is copied to a ``StarLayerGraph`` through
``_rdflib_bridge``, the old function runs, and the shapes graph is copied back into a new ``OxGraph``. A native port over
pyoxigraph terms would replace this module only.
"""

from __future__ import annotations

from typing import Any

from starlayer.graph.oxgraph import _rdflib_bridge as bridge

SH = "http://www.w3.org/ns/shacl#"


def _as_rdflib(x: Any, prefixes: dict[str, str]) -> Any:
    if hasattr(x, "store") and hasattr(x, "triples") and getattr(x, "engine_terms", False):
        return bridge.starlayer_graph(x.triples(), getattr(x, "prefixes", prefixes))
    return x  # already an rdflib graph


def derive_shape(g: Any, template_shape: Any = None, *, ignored_properties: Any = None, use_default_ignored_properties: bool = True) -> Any:
    """One closed ``sh:NodeShape`` per ``rdf:type`` found in ``g``, optionally reconciled with ``template_shape`` (an
    ``OxGraph`` / ``OxDataset`` or an rdflib graph). ``ignored_properties`` are pyoxigraph ``NamedNode``s (or rdflib IRIs)."""
    from starlayer.graph.graph.shape_derivation import derive_shape as old_derive
    from starlayer.graph.oxgraph.core import OxGraph

    data = bridge.starlayer_graph(g.triples(), g.prefixes)
    template = None if template_shape is None else _as_rdflib(template_shape, g.prefixes)
    ignored = None if ignored_properties is None else [bridge.to_rdflib_term(p) for p in ignored_properties]
    result = old_derive(data, template, ignored_properties=ignored, use_default_ignored_properties=use_default_ignored_properties)
    out = OxGraph(prefixes=dict(g.prefixes))
    out.prefixes.setdefault("sh", SH)
    out.extend(tuple(bridge.from_rdflib_term(t) for t in triple) for triple in result)
    return out
