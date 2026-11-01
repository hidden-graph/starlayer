"""Format names to ``pyoxigraph.RdfFormat``.

``turtle`` means Turtle 1.2 and keeps lexical forms as written; ``turtle12`` is an alias. ``n3`` is read and written as Turtle.
TriX, HexTuples and ``longturtle`` are not available (the first was dropped; see docs/working/oxgraph-wrapper.md).
"""

from __future__ import annotations

import pyoxigraph as ox

_F = ox.RdfFormat
_NAMES: dict[str, ox.RdfFormat] = {}
for _names, _fmt in (
    (("turtle", "turtle12", "ttl", "text/turtle", "n3", "text/n3"), _F.TURTLE),
    (("trig", "trig12", "application/trig"), _F.TRIG),
    (("nt", "nt12", "ntriples", "n-triples", "application/n-triples", "nt11"), _F.N_TRIPLES),
    (("nq", "nq12", "nquads", "n-quads", "application/n-quads"), _F.N_QUADS),
    (("xml", "rdf-xml", "rdfxml", "rdf/xml", "pretty-xml", "application/rdf+xml"), _F.RDF_XML),
    (("json-ld", "jsonld", "application/ld+json"), _F.JSON_LD),
):
    for _n in _names:
        _NAMES[_n] = _fmt

#: formats whose documents carry named graphs
QUAD_FORMATS = (_F.TRIG, _F.N_QUADS)
#: how a format is reached when given a file extension
_EXT = {"ttl": _F.TURTLE, "n3": _F.TURTLE, "trig": _F.TRIG, "nt": _F.N_TRIPLES, "nq": _F.N_QUADS, "rdf": _F.RDF_XML,
        "xml": _F.RDF_XML, "owl": _F.RDF_XML, "jsonld": _F.JSON_LD, "json": _F.JSON_LD}


def to_format(name: str | ox.RdfFormat | None, *, default: ox.RdfFormat = _F.TURTLE) -> ox.RdfFormat:
    if name is None:
        return default
    if isinstance(name, ox.RdfFormat):
        return name
    try:
        return _NAMES[str(name).lower()]
    except KeyError:
        raise ValueError(
            f"unknown RDF format {name!r}; known: {', '.join(sorted(n for n in _NAMES if '/' not in n))}"
        ) from None


def format_from_path(path: str) -> ox.RdfFormat | None:
    return _EXT.get(str(path).rsplit(".", 1)[-1].lower()) if "." in str(path) else None
