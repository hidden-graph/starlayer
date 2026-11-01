"""qname helpers over the graph's plain prefix dict (``{prefix: namespace}``); there is no NamespaceManager.

``qname`` / ``compute_qname`` / ``expand_curie`` as rdflib's namespace manager offers them: the longest bound namespace that
leaves a valid local name wins; with ``generate=True`` an unbound namespace gets a fresh ``ns1``, ``ns2``... prefix, which is
added to the dict (rdflib binds it too).
"""

from __future__ import annotations

import re
from typing import Any

import pyoxigraph as ox

from starlayer.graph.oxgraph.pretty import _PN_LOCAL

# Turtle 1.2 PN_LOCAL (the grammar's own character classes, no backslash escapes: an IRI that needs one has no qname) or empty
_LOCAL = re.compile(rf"(?:{_PN_LOCAL.pattern})?")
_SPLIT = re.compile(r"^(.*[/#:])([^/#:]*)$")


def _iri(uri: Any) -> str:
    if isinstance(uri, ox.NamedNode):
        return uri.value
    if isinstance(uri, str):
        return str(uri)
    raise TypeError(f"expected an IRI, got {type(uri).__name__}")


def compute_qname(prefixes: dict[str, str], uri: Any, generate: bool = True) -> tuple[str, str, str]:
    """``(prefix, namespace, local)`` for an IRI. Raises ``KeyError`` when no bound namespace fits and ``generate`` is false,
    ``ValueError`` when the IRI cannot be split at all."""
    iri = _iri(uri)
    best: tuple[str, str] | None = None
    for prefix, ns in prefixes.items():
        ns = str(ns)
        if ns and iri.startswith(ns) and _LOCAL.fullmatch(iri[len(ns) :]) and (best is None or len(ns) > len(best[1])):
            best = (prefix, ns)
    if best is not None:
        return best[0], best[1], iri[len(best[1]) :]
    m = _SPLIT.match(iri)
    if m is None or not _LOCAL.fullmatch(m.group(2)) or not m.group(2):
        raise ValueError(f"cannot split {iri!r} into a namespace and a local name")
    ns, local = m.groups()
    if not generate:
        raise KeyError(f"no prefix is bound for {ns!r}")
    n = 1
    while f"ns{n}" in prefixes:
        n += 1
    prefixes[f"ns{n}"] = ns
    return f"ns{n}", ns, local


def qname(prefixes: dict[str, str], uri: Any) -> str:
    """``prefix:local`` for an IRI (just ``local`` for the empty prefix, as rdflib does)."""
    prefix, _ns, local = compute_qname(prefixes, uri)
    return f"{prefix}:{local}" if prefix else local


def expand_curie(prefixes: dict[str, str], curie: str) -> ox.NamedNode:
    """The IRI of ``prefix:local``; an absolute IRI in angle brackets or with a scheme the dict does not bind is taken as is."""
    if not isinstance(curie, str):
        raise TypeError("expand_curie() needs a str")
    if curie.startswith("<") and curie.endswith(">"):
        return ox.NamedNode(curie[1:-1])
    prefix, sep, local = curie.partition(":")
    if sep and prefix in prefixes:
        return ox.NamedNode(str(prefixes[prefix]) + local)
    if sep:
        return ox.NamedNode(curie)
    raise ValueError(f"{curie!r} is not a CURIE")


_XSD_STRING = "http://www.w3.org/2001/XMLSchema#string"


def n3(prefixes: dict[str, str], term: Any) -> str:
    """The N3 / Turtle form of any term with IRIs abbreviated by the bound prefixes (``ex:alice``, ``"5"^^xsd:integer``,
    ``_:b0``, ``<<( ex:s ex:p ex:o )>>``). An IRI no bound namespace fits stays ``<iri>``; the dict is never changed.
    ``str(term)`` is the unabbreviated form."""
    if isinstance(term, ox.NamedNode):
        try:
            prefix, _ns, local = compute_qname(prefixes, term, generate=False)
        except (KeyError, ValueError):
            return f"<{term.value}>"
        return f"{prefix}:{local}"
    if isinstance(term, ox.Literal):
        text = str(term)
        dt = term.datatype
        if term.language is None and dt.value != _XSD_STRING and text.endswith(f"^^<{dt.value}>"):
            return text[: -len(f"<{dt.value}>")] + n3(prefixes, dt)
        return text
    if isinstance(term, ox.Triple):
        return f"<<( {n3(prefixes, term.subject)} {n3(prefixes, term.predicate)} {n3(prefixes, term.object)} )>>"
    if isinstance(term, ox.BlankNode):
        return str(term)
    if isinstance(term, tuple) and len(term) == 3:
        return n3(prefixes, ox.Triple(*term))
    raise TypeError(f"not an RDF term: {type(term).__name__}")
