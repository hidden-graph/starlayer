"""Canonical entailment regime IRIs, from the SPARQL 1.2 Entailment Regimes
spec (https://www.w3.org/TR/sparql12-entailment/) - fetched directly, not
invented. These are the values both ``infer()``'s ``entailment=`` and
``query()``'s own ``entailment=`` accept, and the same IRIs a SHACL shapes
graph's own ``sh:entailment`` triples carry (see
``starlayer.shacl.engine.entailment``), so every layer speaks one vocabulary with
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

``None`` (simple entailment / no entailment) deliberately has no IRI and is not a regime. A regime is named by text or an IRI
(``regime_name``: any other type is a ``TypeError``); a name that is not one of the four registered regimes raises
``ExecutionError`` of kind ``"unsupported"`` (``unsupported_regimes``: context ``"entailment regime"``, the message lists the
available regimes and the closest name). That includes D-Entailment, a known regime the library does not implement.

``KNOWN_REGIMES`` and ``SUPPORTED_REGIMES`` are sets of IRI text (``str``).
"""

from __future__ import annotations

import difflib
from collections.abc import Iterable
from typing import Any

import pyoxigraph as ox

from starlayer.errors import ExecutionError

__all__ = [
    "D_REGIME",
    "ENTAILMENT",
    "KNOWN_REGIMES",
    "OWL_DIRECT_REGIME",
    "OWL_RL_REGIME",
    "RDFS_REGIME",
    "RDF_REGIME",
    "SUPPORTED_REGIMES",
    "regime_name",
    "unsupported_regimes",
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


def regime_name(value: Any) -> str:
    """The text of an entailment regime named by ``value``: text or an IRI (``NamedNode``). Any other type is a ``TypeError``;
    whether the name is a registered regime is ``unsupported_regimes``' question."""
    if isinstance(value, ox.NamedNode):
        return value.value
    if isinstance(value, str):
        return str(value)  # a str subclass (rdflib's URIRef) hashes differently, so it becomes plain text
    raise TypeError(f"an entailment regime is named by text or an IRI, not {type(value).__name__}: {value!r}")


def unsupported_regimes(names: Iterable[str]) -> ExecutionError | None:
    """``None`` when every name is a registered regime (``SUPPORTED_REGIMES``); otherwise the ``ExecutionError`` of kind
    ``"unsupported"`` (context ``"entailment regime"``) the caller raises: it lists the available regimes and, for each name
    that is close to one, ``did you mean``. D-Entailment is known but not implemented, so it is unsupported too."""
    bad = sorted({n for n in names if n not in SUPPORTED_REGIMES})
    if not bad:
        return None
    available = sorted(SUPPORTED_REGIMES)
    by_local_name = {iri.rsplit("/", 1)[-1].lower(): iri for iri in available}  # "rdfs" finds .../RDFS, "owl-direct" finds .../OWL-Direct
    parts = []
    for name in bad:
        close = difflib.get_close_matches(name.rsplit("/", 1)[-1].lower(), list(by_local_name), n=1, cutoff=0.6) if name != D_REGIME else []
        parts.append(f"{name!r} (did you mean {by_local_name[close[0]]!r}?)" if close else repr(name))
    message = f"Unsupported entailment regime(s) {', '.join(parts)}; the available regimes are {available!r}."
    if D_REGIME in bad:
        message += " ENTAILMENT.D (D-Entailment) is a recognized regime IRI but not implemented."
    return ExecutionError(message, kind="unsupported", context="entailment regime")
