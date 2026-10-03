"""starlayer - the full StarLayer RDF 1.2 stack in one import.

Re-exports the handful of names most guides reach for first - the core
graph/dataset classes and value types from ``starlayer.graph``, plus
``StarLayerShacl`` from ``starlayer.shacl`` - so a first import doesn't
need to know which of the three subpackages (``starlayer.graph``,
``starlayer.sparql``, ``starlayer.shacl`` - formerly three separately
installed packages, `starlayergraph`/`starsparql`/`starshacl`, merged into
one real package here since they were already inseparable in practice -
see `packages/starlayer/docs/`) a given name lives in. Every name here is
the exact same object as its source subpackage's own export; nothing is
redefined, wrapped, or copied.

This is a deliberately small, curated surface, not a flattened namespace
over all three subpackages - ``starlayer.shacl`` and ``starlayer.sparql``
each expose a ``validate()`` function with different signatures and
meanings (SHACL validation vs. SPARQL-algebra-graph validation), so
blindly re-exporting everything from both would silently shadow one with
the other. For anything not re-exported here, import from the owning
subpackage directly (e.g. ``starlayer.sparql.prepare_query_12``,
``starlayer.sparql.srl_eval.srl_infer``, ``starlayer.shacl.close_shape``).
"""

from .graph import (
    BNode,
    Dataset,
    DirLangString,
    Graph,
    Literal,
    Namespace,
    RDF,
    RDFS,
    StarLayerDataset,
    StarLayerGraph,
    TripleTerm,
    URIRef,
    Variable,
    XSD,
)
from .shacl import StarLayerShacl

# Exposes the ontology/shapes registry as starlayer.registry.* without a
# caller needing a separate `import starlayer.registry` - e.g.
# `starlayer.registry.list_ontologies()` works right after a plain `import
# starlayer`. Lives here (not nested under .graph/.sparql/.shacl) because it
# genuinely cuts across all three - see its own registry module's docstring.
# Renamed from starlayer.ontology (2026-10-03) - it holds no ontology
# content of its own, just a name-based lookup over where each vocabulary's
# own graph()/validate() actually live.
# Safe to import eagerly: starlayer.registry itself only eagerly imports
# starontology (a leaf dependency, no cycle); its own graph/sparql/shacl
# imports are lazy (inside functions) precisely to avoid a circular-import
# deadlock.
import starlayer.registry as registry

__all__ = [
    "BNode",
    "Dataset",
    "DirLangString",
    "Graph",
    "Literal",
    "Namespace",
    "RDF",
    "RDFS",
    "StarLayerDataset",
    "StarLayerGraph",
    "StarLayerShacl",
    "TripleTerm",
    "URIRef",
    "Variable",
    "XSD",
]
