"""RDF 1.2 interoperability over pyoxigraph terms: the "basic encoding" of triple terms.

The encoding is the one in the W3C *RDF 1.2 Interoperability* draft
(https://w3c.github.io/rdf-interop/spec/, an Editor's Draft; non-normative; it may change).
The rules this module implements, quoted from the draft:

* "consists of repeating the following steps until no triple term appears in the graph":
  pick a triple term ``tt = <<( s p o )>>``, then
* "minting a fresh blank node b (i.e., a blank node not yet in use in the graph)",
* adding ``(b, rdf:type, rdf:PropositionForm)``, ``(b, rdf:propositionFormSubject, s)``,
  ``(b, rdf:propositionFormPredicate, p)``, ``(b, rdf:propositionFormObject, o)``, and
* "replacing all occurrences of tt appearing in the graph with b".
* Nested triple terms (algorithm ``basic-encode-triple-term``, step 4.2.1): "Let b', M' and G' be the
  result of invoking basic-encode-triple-term passing o as t and M_i", i.e. the inner term is encoded
  first and its blank node becomes the object of the outer description.
* Repeated identical triple terms (same algorithm, step 3): "Let b be the blank node associated with t
  in M_i, if any", i.e. one blank node per distinct triple term, shared by every occurrence. (The draft
  states this only in the algorithm, not in prose.)
* Datasets: "Basic encoding an RDF dataset consists of basic encoding its default graph and each of its
  named graph. In this case, the fresh blank node assigned to each triple term must not be used in any
  graph of the dataset."
* Information preservation: only "when the input graph either has no triple term appearing in it" is the
  output semantically equivalent to the input; the encoding is not semantically equivalent in general.

The draft is silent on three points; this module chooses, deterministically:

* Which graph holds the four description triples: the graph in which the triple term occurs (each graph
  is encoded on its own, as the draft says; the same triple term in two graphs gets two blank nodes, one
  per graph, all distinct from every blank node of the input).
* Blank-node names: ``bnode_prefix=None`` mints random pyoxigraph blank nodes; a prefix mints
  ``<prefix>0``, ``<prefix>1``, ... in input order (skipping labels already in use), so output is
  reproducible.
* Base-direction literals (``"x"@en--ltr``) are RDF 1.2 only and have no RDF 1.1 form. The draft does not
  mention them. :func:`export_rdf11` applies a policy (see :func:`encode_directions`).

Terms are pyoxigraph's. RDF 1.2 (final) allows a triple term only as an object, so only the object
position is rewritten. There is no RDF 1.1 storage backend: RDF 1.1 output is an export step.
"""

from __future__ import annotations

import os
from collections.abc import Iterable
from typing import IO
from typing import Literal as _Lit

import pyoxigraph as ox

__all__ = [
    "RDF_PROPOSITION_FORM",
    "DIRLANG_NS",
    "BasicEncodingError",
    "to_basic",
    "from_basic",
    "encode_directions",
    "decode_directions",
    "export_rdf11",
    "has_triple_terms",
]

_RDF = "http://www.w3.org/1999/02/22-rdf-syntax-ns#"
RDF_TYPE = ox.NamedNode(_RDF + "type")
RDF_PROPOSITION_FORM = ox.NamedNode(_RDF + "PropositionForm")
PF_SUBJECT = ox.NamedNode(_RDF + "propositionFormSubject")
PF_PREDICATE = ox.NamedNode(_RDF + "propositionFormPredicate")
PF_OBJECT = ox.NamedNode(_RDF + "propositionFormObject")
_PF_PREDS = (PF_SUBJECT, PF_PREDICATE, PF_OBJECT)

# Same namespace as starlayer.graph.model.encoding.DIRLANG_NS (checked by a test); repeated here so this
# module does not import rdflib.
DIRLANG_NS = "https://github.com/hidden-graph/starlayergraph/ns/dirlang#"


class BasicEncodingError(ValueError):
    """The input cannot be (de)coded: ambiguous, incomplete or cyclic PropositionForm structure, or
    input that already uses the encoding vocabulary."""


def _as_quads(data) -> list[ox.Quad]:
    out = []
    for item in data:
        if isinstance(item, ox.Triple):
            item = ox.Quad(item.subject, item.predicate, item.object, ox.DefaultGraph())
        out.append(item)
    return out


def has_triple_terms(quads: Iterable) -> bool:
    return any(isinstance(q.object, ox.Triple) for q in _as_quads(quads))


# ----------------------------------------------------------------------------------------------- to_basic


def to_basic(quads: Iterable, *, bnode_prefix: str | None = None) -> list[ox.Quad]:
    """Apply the basic encoding: every triple term becomes a fresh blank node described by four
    ``rdf:PropositionForm`` triples in the graph where the term occurs. Returns a new list of quads with
    no triple term; a dataset without triple terms is returned unchanged (as a list).

    ``quads`` may be a ``Store``, ``Dataset`` or any iterable of ``Quad``/``Triple``.
    Raises :class:`BasicEncodingError` if the input has triple terms and already uses ``rdf:PropositionForm`` or the
    ``rdf:propositionForm*`` predicates (``from_basic`` could not tell it from an encoding)."""
    quads = _as_quads(quads)
    if not any(isinstance(q.object, ox.Triple) for q in quads):
        return quads  # nothing to encode (also makes to_basic idempotent on encoded data)
    used = set()
    for q in quads:
        if isinstance(q.subject, ox.BlankNode):
            used.add(q.subject.value)
        if isinstance(q.object, ox.BlankNode):
            used.add(q.object.value)
        if isinstance(q.graph_name, ox.BlankNode):
            used.add(q.graph_name.value)
        _collect_bnodes(q.object, used)
        if q.predicate in _PF_PREDS or (q.predicate == RDF_TYPE and q.object == RDF_PROPOSITION_FORM):
            raise BasicEncodingError(f"input already uses the PropositionForm vocabulary: {q}")
    counter = [0]

    def fresh() -> ox.BlankNode:
        if bnode_prefix is None:
            while True:
                b = ox.BlankNode()
                if b.value not in used:
                    break
        else:
            while True:
                label = f"{bnode_prefix}{counter[0]}"
                counter[0] += 1
                if label not in used:
                    b = ox.BlankNode(label)
                    break
        used.add(b.value)
        return b

    out: list[ox.Quad] = []
    memo: dict[tuple, ox.BlankNode] = {}  # (graph, triple term) -> blank node: the draft's M_i

    def encode(t: ox.Triple, g, extra: list) -> ox.BlankNode:
        key = (g, t)
        if key in memo:
            return memo[key]
        o = t.object
        if isinstance(o, ox.Triple):
            o = encode(o, g, extra)  # inner term first
        b = fresh()
        memo[key] = b
        extra.append(ox.Quad(b, RDF_TYPE, RDF_PROPOSITION_FORM, g))
        extra.append(ox.Quad(b, PF_SUBJECT, t.subject, g))
        extra.append(ox.Quad(b, PF_PREDICATE, t.predicate, g))
        extra.append(ox.Quad(b, PF_OBJECT, o, g))
        return b

    for q in quads:
        if isinstance(q.object, ox.Triple):
            extra: list = []
            b = encode(q.object, q.graph_name, extra)
            out.append(ox.Quad(q.subject, q.predicate, b, q.graph_name))
            out.extend(extra)
        else:
            out.append(q)
    return out


def _collect_bnodes(term, used: set) -> None:
    """Add the labels of the blank nodes inside a triple term."""
    if isinstance(term, ox.Triple):
        for part in (term.subject, term.object):
            if isinstance(part, ox.BlankNode):
                used.add(part.value)
            else:
                _collect_bnodes(part, used)


# --------------------------------------------------------------------------------------------- from_basic


def from_basic(quads: Iterable, *, accept_iri_nodes: bool = False) -> list[ox.Quad]:
    """Inverse of :func:`to_basic`: recognise the PropositionForm structure in each graph and rebuild
    triple terms (nested and shared ones included). The identity up to blank-node labels:
    ``from_basic(to_basic(x))`` equals ``x`` and keeps its blank nodes.

    A node is a proposition form if it has an ``rdf:type rdf:PropositionForm`` triple. Refused with
    :class:`BasicEncodingError` (never guessed):

    * a form without exactly one subject, one predicate and one object, or with more than one type triple
      for the vocabulary, or description predicates on a node that is not typed (dangling);
    * a form whose components cannot make a triple (a literal or triple term as subject, a non-IRI
      predicate) or that is part of a cycle;
    * a form used anywhere but as an object (as a subject, predicate or graph name), or carrying statements
      other than its description;
    * a form that is not referenced from any other quad (it would vanish).

    ``accept_iri_nodes=True`` also treats IRI-named forms (the old content-hash ``tt:`` IRIs) as triple
    terms; by default only blank nodes qualify, as in the draft."""
    quads = _as_quads(quads)
    by_graph: dict = {}
    for q in quads:
        by_graph.setdefault(q.graph_name, []).append(q)
    graph_names = {g for g in by_graph if not isinstance(g, ox.DefaultGraph)}
    out: list[ox.Quad] = []
    for g, qs in by_graph.items():
        out.extend(_decode_graph(g, qs, graph_names, accept_iri_nodes))
    return out


def _decode_graph(g, qs, graph_names, accept_iri) -> list[ox.Quad]:
    def eligible(n) -> bool:
        return isinstance(n, ox.BlankNode) or (accept_iri and isinstance(n, ox.NamedNode))

    typed: dict = {}
    desc: dict = {}
    for q in qs:
        if q.predicate == RDF_TYPE and q.object == RDF_PROPOSITION_FORM:
            if not eligible(q.subject):
                raise BasicEncodingError(f"{q.subject} is typed rdf:PropositionForm but is not a blank node")
            typed[q.subject] = typed.get(q.subject, 0) + 1
        elif q.predicate in _PF_PREDS:
            desc.setdefault(q.subject, {}).setdefault(q.predicate, []).append(q.object)
    for n, c in typed.items():
        if c > 1:
            raise BasicEncodingError(f"{n} has more than one rdf:type rdf:PropositionForm triple")
    for n in desc:
        if n not in typed:
            raise BasicEncodingError(f"{n} has propositionForm* triples but no rdf:type rdf:PropositionForm")
    for n in typed:
        d = desc.get(n, {})
        for p in _PF_PREDS:
            k = len(d.get(p, []))
            if k != 1:
                raise BasicEncodingError(f"proposition form {n} has {k} values for {p.value.rsplit('#', 1)[1]} (need 1)")
        if n in graph_names:
            raise BasicEncodingError(f"proposition form {n} is also used as a graph name")

    memo: dict = {}
    stack: list = []

    def resolve(n) -> ox.Triple:
        if n in memo:
            return memo[n]
        if n in stack:
            raise BasicEncodingError(f"cyclic proposition form at {n}")
        stack.append(n)
        d = desc[n]
        s, p, o = d[PF_SUBJECT][0], d[PF_PREDICATE][0], d[PF_OBJECT][0]
        if s in typed:
            raise BasicEncodingError(f"proposition form {n} has a triple term as subject ({s})")
        if o in typed:
            o = resolve(o)
        if not isinstance(s, (ox.NamedNode, ox.BlankNode)):
            raise BasicEncodingError(f"proposition form {n}: subject {s} cannot be a triple subject")
        if not isinstance(p, ox.NamedNode):
            raise BasicEncodingError(f"proposition form {n}: predicate {p} is not an IRI")
        stack.pop()
        memo[n] = ox.Triple(s, p, o)
        return memo[n]

    for n in typed:
        resolve(n)

    referenced: set = set()
    out: list[ox.Quad] = []
    for q in qs:
        if q.subject in typed and (q.predicate in _PF_PREDS or (q.predicate == RDF_TYPE and q.object == RDF_PROPOSITION_FORM)):
            continue  # description triple
        if q.subject in typed:
            raise BasicEncodingError(f"proposition form {q.subject} also has other statements ({q.predicate})")
        if q.predicate in typed:
            raise BasicEncodingError(f"proposition form {q.predicate} used as a predicate")
        o = q.object
        if o in typed:
            referenced.add(o)
            o = memo[o]
        out.append(ox.Quad(q.subject, q.predicate, o, q.graph_name))
    # inner forms are referenced by the descriptions of outer ones
    for n in typed:
        o = desc[n][PF_OBJECT][0]
        if o in typed:
            referenced.add(o)
    for n in typed:
        if n not in referenced:
            raise BasicEncodingError(f"proposition form {n} is not referenced by any statement")
    return out


# -------------------------------------------------------------------------------------- base directions


def _dirlang_datatype(lang: str, direction: str) -> ox.NamedNode:
    return ox.NamedNode(f"{DIRLANG_NS}{lang}--{direction}")


def _map_terms(quads: list[ox.Quad], f) -> list[ox.Quad]:
    def term(t):
        if isinstance(t, ox.Triple):
            return ox.Triple(t.subject, t.predicate, term(t.object))
        return f(t)

    return [ox.Quad(q.subject, q.predicate, term(q.object), q.graph_name) for q in quads]


def encode_directions(quads: Iterable, policy: _Lit["datatype", "error", "drop"] = "datatype") -> list[ox.Quad]:
    """Replace base-direction literals, which RDF 1.1 cannot express.

    * ``"datatype"`` (default): ``"x"@en--ltr`` becomes ``"x"^^<DIRLANG_NS#en--ltr>``, the datatype-IRI
      form that ``starlayer.graph.model.encoding.encode_dirlang_datatype`` uses (lossless; reversed by
      :func:`decode_directions`). Lexical form unchanged.
    * ``"error"``: raise ``ValueError``.
    * ``"drop"``: keep the language tag, discard the direction (lossy, still valid RDF 1.1).
    """
    if policy not in ("datatype", "error", "drop"):
        raise ValueError(f"unknown base-direction policy {policy!r}")

    def f(t):
        if isinstance(t, ox.Literal) and t.direction is not None:
            if policy == "error":
                raise ValueError(f"base-direction literal has no RDF 1.1 form: {t}")
            if policy == "drop":
                return ox.Literal(t.value, language=t.language)
            return ox.Literal(t.value, datatype=_dirlang_datatype(t.language, str(t.direction)))
        return t

    return _map_terms(_as_quads(quads), f)


def decode_directions(quads: Iterable) -> list[ox.Quad]:
    """Inverse of ``encode_directions(..., "datatype")``."""

    def f(t):
        if isinstance(t, ox.Literal) and t.datatype.value.startswith(DIRLANG_NS):
            lang, _, d = t.datatype.value[len(DIRLANG_NS):].rpartition("--")
            if lang and d in ("ltr", "rtl"):
                return ox.Literal(t.value, language=lang, direction=ox.BaseDirection.LTR if d == "ltr" else ox.BaseDirection.RTL)
        return t

    return _map_terms(_as_quads(quads), f)


# ------------------------------------------------------------------------------------------------ export

_FORMATS = {
    "turtle": ox.RdfFormat.TURTLE,
    "ttl": ox.RdfFormat.TURTLE,
    "trig": ox.RdfFormat.TRIG,
    "ntriples": ox.RdfFormat.N_TRIPLES,
    "n-triples": ox.RdfFormat.N_TRIPLES,
    "nt": ox.RdfFormat.N_TRIPLES,
    "nquads": ox.RdfFormat.N_QUADS,
    "n-quads": ox.RdfFormat.N_QUADS,
    "nq": ox.RdfFormat.N_QUADS,
    "rdfxml": ox.RdfFormat.RDF_XML,
    "rdf/xml": ox.RdfFormat.RDF_XML,
    "xml": ox.RdfFormat.RDF_XML,
}
_TRIPLE_FORMATS = {ox.RdfFormat.TURTLE, ox.RdfFormat.N_TRIPLES, ox.RdfFormat.RDF_XML}


def export_rdf11(
    store_or_quads,
    format,
    destination: str | os.PathLike | IO[bytes] | None = None,
    prefixes: dict[str, str] | None = None,
    base_iri: str | None = None,
    *,
    bnode_prefix: str | None = None,
    direction_policy: _Lit["datatype", "error", "drop"] = "datatype",
) -> bytes | None:
    """Serialise as RDF 1.1: apply :func:`to_basic`, then the base-direction policy
    (:func:`encode_directions`), assert that no triple term and no directional literal remains, and write
    with pyoxigraph. ``format`` is a ``pyoxigraph.RdfFormat`` or a name (turtle, trig, ntriples, nquads,
    rdfxml). Turtle, N-Triples and RDF/XML hold one graph: a dataset with named graphs is refused. Returns
    the bytes when ``destination`` is None. The output is valid RDF 1.1 but, as the draft warns, not
    semantically equivalent to the RDF 1.2 input when it had triple terms."""
    fmt = _FORMATS[format.lower()] if isinstance(format, str) else format
    if fmt not in _TRIPLE_FORMATS and fmt not in (ox.RdfFormat.TRIG, ox.RdfFormat.N_QUADS):
        raise ValueError(f"not an RDF 1.1 format supported here: {fmt}")
    quads = encode_directions(to_basic(store_or_quads, bnode_prefix=bnode_prefix), direction_policy)
    for q in quads:
        assert not isinstance(q.object, ox.Triple), "triple term survived the basic encoding"
        assert not (isinstance(q.object, ox.Literal) and q.object.direction is not None), "directional literal survived"
    if fmt in _TRIPLE_FORMATS:
        if any(not isinstance(q.graph_name, ox.DefaultGraph) for q in quads):
            raise ValueError(f"{fmt} cannot hold named graphs; use TriG or N-Quads")
        items = [ox.Triple(q.subject, q.predicate, q.object) for q in quads]
    else:
        items = quads
    return ox.serialize(items, destination, format=fmt, prefixes=prefixes, base_iri=base_iri)
