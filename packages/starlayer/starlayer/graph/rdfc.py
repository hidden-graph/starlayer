"""RDF Dataset Canonicalization (RDFC-1.0): the canonical N-Quads text and the hash of a graph or dataset.

A thin front over ``starlayer.graph.rdfc_native`` (Oxigraph's RDFC-1.0), kept as the public entry point of the guides. It takes a
``StarLayerGraph``, ``StarLayerDataset``, ``pyoxigraph.Store`` or an rdflib ``Graph`` / ``Dataset`` (copied into Oxigraph first).
RDFC-1.0 has no triple-term rule, so a triple term is rewritten first with the RDF 1.2 Interoperability basic encoding
(``starlayer.graph.interop.to_basic``); the result is RDFC-1.0 of that RDF 1.1-shaped dataset. A graph without triple terms
gets the plain RDFC-1.0 form and hash that any other implementation computes.

``CanonicalizationComplexityError`` is raised, before canonicalising, for a highly symmetric blank-node structure (the "dataset
poisoning" case of RDFC-1.0 section 7.1), which Oxigraph's canonicaliser would not finish.
"""

from __future__ import annotations

from typing import Any

from starlayer.graph import rdfc_native
from starlayer.graph.compare import as_quads
from starlayer.graph.rdfc_native import CanonicalizationComplexityError

__all__ = ["to_canonical_nquads", "rdfc10_hash", "CanonicalizationComplexityError"]


def to_canonical_nquads(graph: Any, hash_algorithm: str = "sha256") -> str:
    """The canonical N-Quads text of ``graph`` (RDFC-1.0 section 4.4.3 step 7): blank nodes labelled ``c14n0``, ``c14n1``, ...,
    lines sorted. ``hash_algorithm`` is ``"sha256"`` or ``"sha384"`` (the two the specification names); it also drives the
    canonical labelling.

    Raises:
        ValueError: another hash algorithm.
        CanonicalizationComplexityError: a highly symmetric blank-node structure.
    """
    return rdfc_native.canonical_nquads(as_quads(graph), algorithm=hash_algorithm)


def rdfc10_hash(graph: Any, hash_algorithm: str = "sha256") -> str:
    """The hex digest of ``graph``'s canonical N-Quads text, stable under blank-node relabelling.

    Raises:
        ValueError: a hash algorithm other than ``"sha256"`` or ``"sha384"``.
        CanonicalizationComplexityError: a highly symmetric blank-node structure.
    """
    return rdfc_native.canonical_hash(as_quads(graph), algorithm=hash_algorithm)
