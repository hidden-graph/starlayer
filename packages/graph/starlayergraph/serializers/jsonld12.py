"""
starlayergraph.serializers.jsonld12

Serialize a StarLayerGraph to JSON-LD 1.2.

Convention:
  Every triple term is emitted as a top-level JSON-LD node with:
    "@id": "tt:HASH"
    "@type": ["rdf:TripleTerm"]
    "rdf:subject":   [<node>]
    "rdf:predicate": [<node>]
    "rdf:object":    [<node>]

  Triples whose subject or object is a triple term reference that node by its
  tt:HASH URI.  All nested triple terms are emitted as separate top-level nodes
  and cross-referenced the same way.

  The resulting JSON-LD is valid JSON-LD 1.1 — standard JSON-LD parsers produce
  the correct tt: encoding triples, from which StarLayerGraph.parse(format='jsonld12')
  reconstructs the TripleTerm registry via _build_registry_from_store().

Entry point:  serialize_jsonld12(g) -> str
"""

from __future__ import annotations

import json

from rdflib import BNode, Literal, URIRef

from starlayergraph.model.dirlangstring import DirLangString
from starlayergraph.model.encoding import TT_NS, encode_dirlang_datatype
from starlayergraph.model.triple import TripleTerm

_RDF_NS = 'http://www.w3.org/1999/02/22-rdf-syntax-ns#'
_RDF_TRIPLE_TERM = _RDF_NS + 'TripleTerm'

_FIXED_CONTEXT = {
    'rdf': _RDF_NS,
    'tt':  TT_NS,
}


# ---------------------------------------------------------------------------
# Node formatters
# ---------------------------------------------------------------------------

def _uri_value(uri: str) -> dict:
    """Compact a full URI to a prefixed form if it matches a known prefix."""
    if uri.startswith(TT_NS):
        return {'@id': 'tt:' + uri[len(TT_NS):]}
    if uri.startswith(_RDF_NS):
        return {'@id': 'rdf:' + uri[len(_RDF_NS):]}
    return {'@id': uri}


def _node_to_jld(node) -> dict:
    """Convert any rdflib node (or TripleTerm) to a JSON-LD value object."""
    if isinstance(node, TripleTerm):
        # TripleTerms in value position are referenced by their tt:HASH URI.
        # The full TripleTerm definition is emitted as a separate top-level node.
        return {'@id': 'tt:' + _tt_local(node)}
    if isinstance(node, DirLangString):
        # Same internal-datatype-URI encoding as every other format (see
        # starlayergraph.model.encoding) rather than JSON-LD 1.1's native
        # "@language"/"@direction" pair: rdflib's JSON-LD codec (RDF 1.1) has
        # no concept of @direction and would silently drop it on parse. An
        # explicit "@type" round-trips through rdflib's real JSON-LD parser
        # unchanged, the same way rdf:TripleTerm nodes do below.
        dt = str(encode_dirlang_datatype(node.language, node.direction))
        return {'@value': node.value, '@type': dt}
    if isinstance(node, URIRef):
        return _uri_value(str(node))
    if isinstance(node, BNode):
        return {'@id': f'_:{node}'}
    if isinstance(node, Literal):
        if node.language:
            return {'@value': str(node), '@language': node.language}
        if node.datatype and str(node.datatype) != 'http://www.w3.org/2001/XMLSchema#string':
            return {'@value': str(node), '@type': str(node.datatype)}
        return {'@value': str(node)}
    return {'@value': str(node)}


def _tt_local(tt: TripleTerm) -> str:
    """Return the hex local part of the tt:HASH URI for this TripleTerm.

    Avoids importing StarLayerGraph; recomputes the hash on-the-fly.
    For efficiency, callers that already have the URI should pass it directly.
    """
    from starlayergraph.model.encoding import term_key, tt_hash
    s = tt.subject
    p = tt.predicate
    o = tt.object
    s_str = (TT_NS + _tt_local(s)) if isinstance(s, TripleTerm) else term_key(s)
    o_str = (TT_NS + _tt_local(o)) if isinstance(o, TripleTerm) else term_key(o)
    return tt_hash(s_str, term_key(p), o_str)


def _tt_node(tt_local: str, tt: TripleTerm) -> dict:
    """Build the JSON-LD top-level node for one TripleTerm."""
    return {
        '@id':               'tt:' + tt_local,
        '@type':             ['rdf:TripleTerm'],
        _RDF_NS + 'subject':   [_node_to_jld(tt.subject)],
        _RDF_NS + 'predicate': [_node_to_jld(tt.predicate)],
        _RDF_NS + 'object':    [_node_to_jld(tt.object)],
    }


# ---------------------------------------------------------------------------
# Subject-ID helpers
# ---------------------------------------------------------------------------

def _subject_id(s) -> str:
    """Return the string key used as the @id for a triple's subject."""
    if isinstance(s, TripleTerm):
        return 'tt:' + _tt_local(s)
    if isinstance(s, BNode):
        return f'_:{s}'
    return str(s)


def _subject_id_obj(s) -> dict:
    """Return the '@id' dict for a triple's subject (for the node's '@id' field)."""
    sid = _subject_id(s)
    # Compact tt: and rdf: prefixes in @id values too
    if sid.startswith(TT_NS):
        return 'tt:' + sid[len(TT_NS):]
    if sid.startswith(_RDF_NS):
        return 'rdf:' + sid[len(_RDF_NS):]
    return sid


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

def serialize_jsonld12(g) -> str:
    """Serialize a StarLayerGraph to JSON-LD 1.2 text.

    Triple terms are emitted as top-level nodes with ``@type: rdf:TripleTerm``
    and ``rdf:subject / rdf:predicate / rdf:object`` properties.  All other
    nodes follow standard JSON-LD expanded-form conventions.
    """
    nodes: dict[str, dict] = {}   # @id-string -> JSON-LD node object

    def ensure(sid: str) -> dict:
        if sid not in nodes:
            nodes[sid] = {'@id': sid}
        return nodes[sid]

    # 1. Emit a top-level rdf:TripleTerm node for every registered TripleTerm.
    for tt_uri, tt in g._tt_nodes.items():
        local = str(tt_uri)[len(TT_NS):]
        sid   = 'tt:' + local
        node  = ensure(sid)
        node.update(_tt_node(local, tt))

    # 2. Emit regular (user-visible) triples.
    for s, p, o in g.triples((None, None, None)):
        sid  = _subject_id_obj(s)
        node = ensure(sid)
        pstr = str(p)
        # Compact rdf: predicates in the key too
        if pstr.startswith(_RDF_NS):
            pstr = 'rdf:' + pstr[len(_RDF_NS):]
        node.setdefault(pstr, []).append(_node_to_jld(o))

    # 3. Assemble output — TripleTerm nodes first, then subject nodes.
    tt_ids   = {k for k in nodes if k.startswith('tt:')}
    other    = [v for k, v in nodes.items() if k not in tt_ids]
    tt_nodes = [nodes[k] for k in sorted(tt_ids)]

    doc = {
        '@context': _FIXED_CONTEXT,
        '@graph':   tt_nodes + other,
    }
    return json.dumps(doc, indent=2, ensure_ascii=False) + '\n'
