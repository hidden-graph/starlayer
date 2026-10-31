"""Isomorphism and canonical forms over pyoxigraph, using Oxigraph's native RDFC-1.0.

* :func:`isomorphic` canonicalises both datasets natively and compares. Oxigraph's canonicaliser accepts
  triple terms (blank nodes inside them are relabelled consistently), but no specification defines the
  canonical labels of triple terms, so that output must not be compared with another implementation's.
* :func:`canonical_quads`, :func:`canonical_nquads` and :func:`canonical_hash` apply the Interoperability
  draft's basic encoding (:func:`starlayer.graph.interop.to_basic`) first, then RDFC-1.0, so the result
  is RDFC-1.0 of an RDF 1.1-shaped dataset and rests on a documented rewriting. The form is defined by
  that draft and may change with it. RDFC-1.0 has no triple-term rule of its own.

Known limit (checked against the W3C poison test, test074): Oxigraph's canonicaliser has no
denial-of-service defence; a highly symmetric dataset (a clique of 10 blank nodes) does not finish. Do not
canonicalise untrusted input with it without an outer limit; ``starlayer.graph.rdfc`` raises
``CanonicalizationComplexityError`` there.
"""

from __future__ import annotations

import hashlib

import pyoxigraph as ox

from starlayer.graph.interop import to_basic

__all__ = ["isomorphic", "canonical_quads", "canonical_nquads", "canonical_hash"]

_ALGORITHMS = {
    "sha256": ox.CanonicalizationAlgorithm.RDFC_1_0,
    "sha384": ox.CanonicalizationAlgorithm.RDFC_1_0_SHA_384,
}
_HASHES = {"sha256": hashlib.sha256, "sha384": hashlib.sha384}


def _quads(data) -> list[ox.Quad]:
    out = []
    for item in data:
        if isinstance(item, ox.Triple):
            item = ox.Quad(item.subject, item.predicate, item.object, ox.DefaultGraph())
        out.append(item)
    return out


def _algorithm(algorithm) -> tuple[str, ox.CanonicalizationAlgorithm]:
    """Accept "sha256"/"sha384" (RDFC-1.0 with that hash) or a CanonicalizationAlgorithm."""
    if isinstance(algorithm, str):
        key = algorithm.lower().replace("-", "")
        if key not in _ALGORITHMS:
            raise ValueError(f"RDFC-1.0 specifies SHA-256 or SHA-384, not {algorithm!r}")
        return key, _ALGORITHMS[key]
    if algorithm == ox.CanonicalizationAlgorithm.RDFC_1_0:
        return "sha256", algorithm
    if algorithm == ox.CanonicalizationAlgorithm.RDFC_1_0_SHA_384:
        return "sha384", algorithm
    raise ValueError(f"not an RDFC-1.0 algorithm: {algorithm!r}")


def _canonicalize(quads: list[ox.Quad], algorithm) -> list[ox.Quad]:
    _, alg = _algorithm(algorithm)
    ds = ox.Dataset(quads)  # a copy: the caller's store or dataset is never relabelled
    ds.canonicalize(alg)
    return list(ds)


def isomorphic(a, b, *, basic: bool = False) -> bool:
    """True if the two datasets (``Store``, ``Dataset`` or iterables of quads) are isomorphic: equal after
    RDFC-1.0 canonicalisation, so graph names count and blank-node graph names are handled by the
    algorithm. ``basic=True`` applies the basic encoding first (then triple terms are compared as their
    PropositionForm structure, which is also isomorphism-preserving)."""
    qa, qb = _quads(a), _quads(b)
    if basic:
        qa, qb = to_basic(qa), to_basic(qb)
    if len(set(qa)) != len(set(qb)):
        return False
    return set(_canonicalize(qa, "sha256")) == set(_canonicalize(qb, "sha256"))


def canonical_quads(dataset, *, algorithm="sha256", basic: bool = True) -> list[ox.Quad]:
    """The canonical quads, sorted by their N-Quads line. With ``basic=True`` (default) the basic encoding
    is applied first, so no triple term appears in the result."""
    qs = _quads(dataset)
    if basic:
        qs = to_basic(qs)
    return sorted(_canonicalize(qs, algorithm), key=_line)


def _line(q: ox.Quad) -> str:
    return ox.serialize([q], format=ox.RdfFormat.N_QUADS).decode()


def canonical_nquads(dataset, *, algorithm="sha256", basic: bool = True) -> str:
    """Canonical N-Quads text: one line per quad, sorted, as RDFC-1.0 section 4.4.3 step 7 specifies."""
    return "".join(sorted(_line(q) for q in canonical_quads(dataset, algorithm=algorithm, basic=basic)))


def canonical_hash(dataset, *, algorithm="sha256", basic: bool = True) -> str:
    """Hex digest (SHA-256 by default, or SHA-384) of the canonical N-Quads text."""
    key, _ = _algorithm(algorithm)
    return _HASHES[key](canonical_nquads(dataset, algorithm=algorithm, basic=basic).encode("utf-8")).hexdigest()
