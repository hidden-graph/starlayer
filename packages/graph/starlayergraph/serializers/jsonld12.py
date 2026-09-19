"""
starlayergraph.serializers.jsonld12

JSON-LD has no published RDF 1.2 companion specification (unlike Turtle,
N-Triples, N-Quads, TriG, and RDF/XML, which all have real RDF 1.2 companion
documents - see docs/rdf12_sparql12_gap_analysis.md) - so there is no
standard, or even de facto, way to represent a triple term or a
direction-tagged literal in JSON-LD. Confirmed live against both reference
RDF 1.2 engines: Apache Jena/Fuseki 5.5.0 raises HTTP 500 attempting to
serialize a triple term to JSON-LD ("Exception while writing JSON-LD 1.1"),
and Oxigraph returns an explicit "JSON-LD does not support RDF 1.2 yet"
error - neither invents an encoding of its own for content the format
genuinely can't express.

`jsonld12` follows that same model rather than inventing a
starlayergraph-specific encoding: plain RDF 1.1 content serializes as
ordinary JSON-LD (delegating straight to rdflib's own, standard JSON-LD
writer), and a graph containing a triple term or a direction-tagged literal
raises ValueError instead of silently downgrading or producing something
that only round-trips through starlayergraph's own tooling.

An earlier version of this module did invent its own convention (an
`rdf:TripleTerm` node shape keyed by the same tt:HASH URIs used internally,
for round-tripping through starlayergraph's own parser) - replaced with the
explicit-error model here, matching how every other RDF 1.2 engine actually
behaves: a document that *looks* like ordinary JSON-LD but only means what
it means through one specific tool's own private convention isn't really
interchange-format JSON-LD at all.

Entry point: serialize_jsonld12(g) -> str
"""

from __future__ import annotations

from starlayergraph.model.dirlangstring import DirLangString
from starlayergraph.model.triple import TripleTerm


def _find_rdf12_content(g) -> str | None:
    """Return a short description of the first triple term or
    direction-tagged literal found in `g`'s object position, or None if `g`
    is pure RDF 1.1 content.

    Object position only: a TripleTerm is never legal as a subject (RDF
    1.2's own triple-formation rules, already enforced at construction -
    see TripleTerm's own validation), and a nested triple term is always
    reachable this way too - it can only appear nested inside an *outer*
    triple term, which is itself some triple's object, so scanning object
    position alone is enough to detect either shape anywhere in the graph.
    """
    for _s, _p, o in g.triples((None, None, None)):
        if isinstance(o, TripleTerm):
            return 'a triple term (<<( )>>)'
        if isinstance(o, DirLangString):
            return 'a direction-tagged literal (@lang--dir)'
    return None


def serialize_jsonld12(g) -> str:
    """Serialize a StarLayerGraph to JSON-LD.

    Delegates entirely to rdflib's own, standard JSON-LD writer for plain
    RDF 1.1 content. Raises ValueError if `g` contains a triple term or a
    direction-tagged literal - see this module's own docstring for why
    there's no fallback encoding to use instead.
    """
    found = _find_rdf12_content(g)
    if found is not None:
        raise ValueError(
            f"RDF 1.2: JSON-LD has no published RDF 1.2 companion spec, so it "
            f"cannot represent {found} - this graph contains one. Serialize as "
            f"'turtle12', 'longturtle12', 'nt12', 'nq12', 'trig12', 'trix12', "
            f"or 'rdfxml12' instead."
        )
    return g._deskolemize_to_graph().serialize(format='json-ld')
