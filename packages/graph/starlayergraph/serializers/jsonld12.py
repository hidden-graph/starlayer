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

_FIXED_PREFIXES = (
    # (namespace, prefix) - always available for compaction, regardless of
    # whether the graph itself has them bound, since the tt:HASH encoding
    # and rdf:TripleTerm/subject/predicate/object vocabulary are intrinsic
    # to this format, not something the caller opts into via g.bind().
    (TT_NS, 'tt'),
    (_RDF_NS, 'rdf'),
)


# ---------------------------------------------------------------------------
# Prefix compaction
# ---------------------------------------------------------------------------

def _collect_used_prefixes(g) -> list:
    """Return (namespace, prefix) pairs from g's own bindings that are
    actually used by some URI in the graph - keeps @context from being
    padded out with rdflib's ~30 default bindings (skos, foaf, dcterms, ...)
    that this particular graph never references.

    Longest-namespace-first, so a URI matches its most specific bound
    namespace rather than an accidental shorter prefix of it.
    """
    candidates = sorted(
        ((str(ns), str(prefix)) for prefix, ns in g.namespaces() if prefix),
        key=lambda pair: -len(pair[0]),
    )
    if not candidates:
        return []

    used = []
    seen_ns = set()

    def note(uri: str) -> None:
        for ns, prefix in candidates:
            if uri.startswith(ns) and ns not in seen_ns:
                seen_ns.add(ns)
                used.append((ns, prefix))
                return

    for s, p, o in g.triples((None, None, None)):
        for term in (s, p, o):
            if isinstance(term, TripleTerm):
                for component in (term.subject, term.predicate, term.object):
                    if isinstance(component, URIRef):
                        note(str(component))
            elif isinstance(term, URIRef):
                note(str(term))

    return used


def _make_compactor(extra_prefixes: list):
    """Build a compact(uri) -> {'@id': ...} function using the fixed tt:/rdf:
    prefixes plus whatever else this graph actually uses, longest match first.
    """
    table = sorted(
        list(_FIXED_PREFIXES) + list(extra_prefixes),
        key=lambda pair: -len(pair[0]),
    )

    def compact(uri: str) -> dict:
        for ns, prefix in table:
            if uri.startswith(ns):
                return {'@id': f'{prefix}:{uri[len(ns):]}'}
        return {'@id': uri}

    return compact, {prefix: ns for ns, prefix in table}


# ---------------------------------------------------------------------------
# Node formatters
# ---------------------------------------------------------------------------

def _node_to_jld(node, compact) -> dict:
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
        return compact(str(node))
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


def _tt_node(tt_local: str, tt: TripleTerm, compact) -> dict:
    """Build the JSON-LD top-level node for one TripleTerm."""
    return {
        '@id':           'tt:' + tt_local,
        '@type':         ['rdf:TripleTerm'],
        'rdf:subject':   [_node_to_jld(tt.subject, compact)],
        'rdf:predicate': [_node_to_jld(tt.predicate, compact)],
        'rdf:object':    [_node_to_jld(tt.object, compact)],
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


def _subject_id_compacted(s, compact) -> str:
    """Return the compacted string used as the @id for a triple's subject."""
    sid = _subject_id(s)
    if sid.startswith('tt:') or sid.startswith('_:'):
        return sid
    return compact(sid)['@id']


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

def serialize_jsonld12(g) -> str:
    """Serialize a StarLayerGraph to JSON-LD 1.2 text.

    Triple terms are emitted as top-level nodes with ``@type: rdf:TripleTerm``
    and ``rdf:subject / rdf:predicate / rdf:object`` properties, compacted
    the same way every other key/value in the document is. ``@context``
    always carries ``tt:``/``rdf:`` (intrinsic to the encoding) plus whatever
    other namespaces this graph has bound *and* actually uses - so e.g. a
    graph with ``g.bind("ex", ...)`` gets ``ex:alice`` in the output instead
    of a raw ``http://example.org/alice``, the same compaction every other
    StarLayer format (turtle12, trig12, ...) already gives you.
    """
    extra_prefixes = _collect_used_prefixes(g)
    compact, context = _make_compactor(extra_prefixes)

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
        node.update(_tt_node(local, tt, compact))

    # 2. Emit regular (user-visible) triples.
    for s, p, o in g.triples((None, None, None)):
        sid  = _subject_id_compacted(s, compact)
        node = ensure(sid)
        pstr = compact(str(p))['@id']
        node.setdefault(pstr, []).append(_node_to_jld(o, compact))

    # 3. Assemble output — TripleTerm nodes first, then subject nodes.
    tt_ids   = {k for k in nodes if k.startswith('tt:')}
    other    = [v for k, v in nodes.items() if k not in tt_ids]
    tt_nodes = [nodes[k] for k in sorted(tt_ids)]

    doc = {
        '@context': context,
        '@graph':   tt_nodes + other,
    }
    return json.dumps(doc, indent=2, ensure_ascii=False) + '\n'
