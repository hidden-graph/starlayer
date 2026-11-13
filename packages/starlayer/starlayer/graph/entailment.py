"""Canonical entailment regime IRIs, from the SPARQL 1.2 Entailment Regimes
spec (https://www.w3.org/TR/sparql12-entailment/) - fetched directly, not
invented. These are the values both ``infer()``'s ``entailment=`` and
``query()``'s own ``entailment=`` accept, and the same IRIs a SHACL shapes
graph's own ``sh:entailment`` triples carry (see
``starlayer.shacl_engine.entailment``), so every layer speaks one vocabulary with
no separate translation table in between.

``ENTAILMENT`` is a namespace of pyoxigraph ``NamedNode`` constants, not individual module-
level constants - ``http://www.w3.org/ns/entailment/`` {RDF, RDFS} both
collide by bare name with the commonly-imported ``RDF``/``RDFS`` namespace
objects, so every real caller needs the
qualified ``ENTAILMENT.RDF``/``ENTAILMENT.RDFS`` form regardless; the two
hyphenated regime names (``OWL-RDF-Based``/``OWL-Direct``) need bracket
access (``ENTAILMENT["OWL-RDF-Based"]``) since a hyphen isn't valid in a
Python attribute name.

``ENTAILMENT["OWL-RDF-Based"]``'s coverage here is the OWL 2 RL *fragment*
of the full OWL 2 RDF-Based Semantics regime (rule-based, via ``owlrl`` in the ``starlayer-reasoning`` package) -
not the complete regime, which is undecidable in general. Full OWL 2
RDF-Based Semantics and D-Entailment/RIF Core Entailment have no
implementation here and are not planned - see
``docs/design/future_enhancements.md``.

``ENTAILMENT["OWL-Direct"]`` is the one regime both ``infer()`` and
``query()`` dispatch to for OWL 2 Direct Semantics (tableau) reasoning, which
the ``starlayer-reasoning`` package provides -
a single name and IRI for a single regime, used uniformly by both methods.

``None`` (simple entailment / no entailment) deliberately has no IRI and is not a regime. ``query()`` accepts no other
value than ``None`` and the four regime IRIs; anything else raises ``NotImplementedError``.

``KNOWN_REGIMES`` and ``SUPPORTED_REGIMES`` are sets of IRI text (``str``).
"""

from __future__ import annotations

import pyoxigraph as ox

__all__ = [
    "D_REGIME",
    "ENTAILMENT",
    "KNOWN_REGIMES",
    "OWL_DIRECT_REGIME",
    "OWL_RL_REGIME",
    "RDFS_REGIME",
    "RDF_REGIME",
    "SUPPORTED_REGIMES",
]

_ENTAILMENT_BASE = "http://www.w3.org/ns/entailment/"


class _EntailmentNamespace:
    """``ENTAILMENT.RDFS``, ``ENTAILMENT["OWL-Direct"]``: the regime IRIs of the SPARQL 1.2 Entailment Regimes spec, as ``NamedNode``s."""

    def __getitem__(self, name: str) -> ox.NamedNode:
        return ox.NamedNode(_ENTAILMENT_BASE + name)

    def __getattr__(self, name: str) -> ox.NamedNode:
        if name.startswith("_"):
            raise AttributeError(name)
        return self[name]


ENTAILMENT = _EntailmentNamespace()
RDF_REGIME = ENTAILMENT.RDF.value
RDFS_REGIME = ENTAILMENT.RDFS.value
D_REGIME = ENTAILMENT.D.value
OWL_RL_REGIME = ENTAILMENT["OWL-RDF-Based"].value
OWL_DIRECT_REGIME = ENTAILMENT["OWL-Direct"].value
KNOWN_REGIMES = frozenset({RDF_REGIME, RDFS_REGIME, D_REGIME, OWL_RL_REGIME, OWL_DIRECT_REGIME})
SUPPORTED_REGIMES = frozenset({RDF_REGIME, RDFS_REGIME, OWL_RL_REGIME, OWL_DIRECT_REGIME})
