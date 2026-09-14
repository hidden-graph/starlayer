"""starlayer - the full StarLayer RDF 1.2 stack in one import.

Re-exports the handful of names most guides reach for first - the core
graph/dataset classes and value types from ``starlayergraph``, plus
``StarShaclValidator`` from ``starshacl`` - so a first import doesn't need
to know which of the three underlying packages (``starlayergraph``,
``starsparql``, ``starshacl``) a given name lives in. Every name here is
the exact same object as its source package's own export; nothing is
redefined, wrapped, or copied.

This is a deliberately small, curated surface, not a flattened namespace
over all three packages - ``starshacl`` and ``starsparql`` each expose a
``validate()`` function with different signatures and meanings (SHACL
validation vs. SPARQL-algebra-graph validation), so blindly re-exporting
everything from both would silently shadow one with the other. For
anything not re-exported here, import from the owning package directly.
"""

from starlayergraph import (
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
from starshacl import StarShaclValidator

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
    "StarShaclValidator",
    "TripleTerm",
    "URIRef",
    "Variable",
    "XSD",
]
