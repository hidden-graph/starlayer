"""Graph comparison utilities, RDF 1.2 (triple-term) aware.

``rdflib.compare``'s isomorphism/canonicalization algorithm predates RDF 1.2
and knows nothing about triple terms (``starlayer.graph.model.triple.TripleTerm``,
the ``<<( s p o )>>`` syntax) - confirmed live two ways:

- ``rdflib.compare.isomorphic()`` silently gives the WRONG answer for two
  graphs that are genuinely isomorphic but differ only in an arbitrary
  blank-node label nested *inside* a triple term - the blank node is hidden
  from rdflib's own blank-node adjacency discovery (``_TripleCanonicalizer.
  _initial_color()``), which only inspects top-level ``(s, p, o)`` positions,
  so it never even enters the color-refinement process.
- ``rdflib.compare.to_isomorphic()`` crashes outright
  (``AssertionError: Term <<(...)>> must be an rdflib term``), since
  ``TripleTerm`` is a plain Python class, not an ``rdflib.term.Node``
  subclass, and ``Graph.addN()`` hard-requires one.

Directional language strings (``"..."@lang--dir``,
``starlayer.graph.model.dirlangstring.DirLangString``) need one line of
handling too, for the same underlying reason as triple terms: public
iteration decodes both to plain, non-``Node`` Python objects (confirmed
live - a naive assumption that ``DirLangString`` "already worked" because
plain ``rdflib.compare.isomorphic()`` tolerates it was wrong: that path
never calls ``Graph.add()``, so it never hits the ``Node``-only
assertion - this module's own ``_decompose()`` does, since it builds a
fresh plain graph). Unlike a triple term, a ``DirLangString`` has no
internal graph structure to descend into - it's just re-encoded as the
same flat ``Literal`` form (via ``encode_dirlang_datatype``) the rest of
this codebase already uses at the read/write boundary, one line, no
recursion.

A third, unrelated gap this module also closes: rdflib's own ``Literal``
treats a "simple literal" (``datatype=None``, no language tag - e.g. plain
``Literal("high")``) as unequal to the same lexical value with an explicit
``xsd:string`` datatype (``Literal("high", datatype=XSD.string)``), even
though RDF 1.1 Concepts defines a simple literal as *sugar for* the
``xsd:string``-typed form, not a distinct value - the two are the same RDF
term. Confirmed live: some of this project's own RDF 1.2 format writers
round-trip a plain literal through an explicit ``^^xsd:string`` (matching
N-Triples/TriX convention) while others don't, so `isomorphic()` calling
straight through to rdflib's own comparison saw genuinely identical graphs
as different depending only on which serializer a document happened to
pass through - a false negative, not a real content difference. Fixed here
by normalizing every explicit-``xsd:string`` literal to its simple-literal
form before handing off to rdflib's algorithm, rather than by changing any
serializer's output (the actual bytes each format writes are a legitimate,
independent choice per format - this is a comparison-correctness fix, not
a formatting one).

This module fixes both problems by decomposing every triple term into a
synthetic RDF-reification-shaped fragment - a *fresh* blank node standing in
for the triple term's own identity, plus three edges (via a dedicated,
collision-safe internal namespace, not ``rdf:subject``/``predicate``/
``object`` - a source graph could legitimately use classic RDF reification
with those exact predicates on its own, unrelated blank nodes, and mixing
the two would corrupt canonicalization) pointing at the triple term's own
subject/predicate/object - recursing for a nested triple term (legal only in
object position, per RDF 1.2's own TRIPLE() rules, which
``TripleTerm.__init__`` already enforces). The decomposed graph has no
triple terms left at all, so rdflib's own (unmodified, already well-tested)
isomorphism/canonicalization algorithm runs against it directly and correctly:

- A *ground* (blank-node-free) triple term decomposes to a blank node whose
  only edges are to other ground terms - two occurrences of the same ground
  triple term value decompose to two structurally-identical, mutually
  interchangeable blank nodes, which color-refinement already resolves to
  the same canonical color on its own. No special-casing needed for
  "shared" ground triple-term values.
- A triple term containing a real blank node decomposes so that blank node
  becomes an ordinary graph-level blank node again, correctly participating
  in the *same* global canonical relabeling as every other blank node in the
  graph (including whatever other triples elsewhere also reference it) -
  exactly the semantics a "descend into triple terms" fix to rdflib's own
  algorithm would achieve, reached here without touching rdflib internals
  at all.

Scope: this fixes the concrete isomorphism/comparison bug using rdflib's
existing digest algorithm (Sayers & Karp sum-of-hashes + traces, per
``IsomorphicGraph``'s own docstring) - it is not yet a spec-compliant
implementation of the actual W3C RDF Dataset Canonicalization (RDFC-1.0)
algorithm, which (confirmed by fetching the spec text directly) doesn't
address triple terms at all - extending RDFC-1.0 itself for RDF 1.2 is
future, larger work, deliberately deferred (see project memory).
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from rdflib import BNode, Graph, Literal, Namespace, URIRef
from rdflib.compare import graph_diff as _rdflib_graph_diff
from rdflib.compare import isomorphic as _rdflib_isomorphic
from rdflib.compare import to_isomorphic as _rdflib_to_isomorphic
from rdflib.namespace import XSD

from starlayer.graph.model.dirlangstring import DirLangString
from starlayer.graph.model.encoding import encode_dirlang_datatype
from starlayer.graph.model.triple import TripleTerm

if TYPE_CHECKING:
    pass

__all__ = ["isomorphic", "graph_diff", "to_isomorphic", "to_canonical_hash"]

# A dedicated, internal-only namespace for the synthetic reification edges -
# never emitted by any parser/serializer in this codebase, so it can never
# collide with a source graph's own use of classic RDF reification
# (rdf:subject/predicate/object) on unrelated blank nodes.
_TT = Namespace("urn:starlayer:canon-tt#")


_TT_PREFIX = str(_TT)


def _escape_predicate(p: Any) -> Any:
    """Keep the decomposition injective: a source predicate in the internal
    namespace is moved under ``..#escaped:`` so it can never be mistaken for
    one of the three synthetic edges (``subject``/``predicate``/``object``)
    that stand for a triple term."""
    if isinstance(p, URIRef) and str(p).startswith(_TT_PREFIX):
        return URIRef(_TT_PREFIX + "escaped:" + str(p)[len(_TT_PREFIX) :])
    return p


def _is_quad_store(graph: Any) -> bool:
    """True for a dataset (``rdflib.Dataset``/``ConjunctiveGraph``,
    ``StarLayerDataset``): something that yields quads, not triples."""
    default = getattr(graph, "default_graph", None)
    if default is None:
        default = getattr(graph, "default_context", None)
    return callable(getattr(graph, "quads", None)) and default is not None


def _quads_of(graph: Any) -> list:
    """Every quad of a dataset as ``(s, p, o, g)``, ``g`` an identifier or
    ``None`` for the default graph (``StarLayerDataset.quads()`` yields a
    graph object in the fourth place, rdflib's ``Dataset`` an identifier)."""
    default = getattr(graph, "default_graph", None)
    if default is None:
        default = getattr(graph, "default_context", None)
    default_id = default.identifier
    out = []
    for s, p, o, g in graph.quads():
        gid = g.identifier if isinstance(g, Graph) else g
        out.append((s, p, o, None if gid == default_id else gid))
    return out


def _decompose_quads(quads: Any) -> list:
    """Quads with every triple term replaced by a synthetic reification
    fragment placed in the same graph as the quad that held the term, see
    the module docstring for why that suffices. Returns de-duplicated quads
    (a set, as a graph would be); the decomposition is injective."""
    out: dict = {}

    def _term(node: Any, g: Any) -> Any:
        """A triple term becomes a fresh blank node (recursing for a nested
        triple term in object position); a DirLangString is re-encoded as
        the same flat Literal form used at this codebase's own read/write
        boundary; an explicit-xsd:string Literal is normalized down to the
        simple-literal form (datatype=None) it's semantically sugar for, per
        RDF 1.1 Concepts (see module docstring); a language tag is
        lower-cased (tags compare case-insensitively); anything else
        (already a plain rdflib term) passes through unchanged."""
        if isinstance(node, TripleTerm):
            tt_node = BNode()
            out[(tt_node, _TT.subject, _term(node.subject, g), g)] = None
            out[(tt_node, _TT.predicate, node.predicate, g)] = None
            out[(tt_node, _TT.object, _term(node.object, g), g)] = None
            return tt_node
        if isinstance(node, DirLangString):
            return Literal(node.value, datatype=encode_dirlang_datatype(node.language, node.direction))
        if isinstance(node, Literal):
            if node.datatype == XSD.string and node.language is None:
                return Literal(str(node))
            if node.language and node.language != node.language.lower():
                return Literal(str(node), lang=node.language.lower())
        return node

    for s, p, o, g in quads:
        out[(_term(s, g), _escape_predicate(p), _term(o, g), g)] = None
    return list(out)


def _decompose(graph: Any) -> Graph:
    """Return a plain ``rdflib.Graph`` with every triple term replaced by a
    synthetic reification fragment - see module docstring for why this is
    sufficient for correct isomorphism/canonicalization.
    """
    out = Graph()
    for s, p, o, _g in _decompose_quads((s, p, o, None) for s, p, o in graph):
        out.add((s, p, o))
    return out


def _canonical_nquads_of(graph: Any) -> str:
    from starlayer.graph.rdfc import to_canonical_nquads

    return to_canonical_nquads(graph)


def _reject_dataset(*graphs: Any) -> None:
    for g in graphs:
        if _is_quad_store(g):
            raise TypeError(
                f"{type(g).__name__} is a dataset: this function compares graphs. "
                "Use compare.isomorphic() or rdfc.to_canonical_nquads() for datasets."
            )


def isomorphic(graph1: Any, graph2: Any) -> bool:
    """RDF-1.2-aware replacement for ``rdflib.compare.isomorphic`` - correct
    for graphs containing triple terms (including ones with nested blank
    nodes), identical to the original for graphs that don't. Also RDF
    1.1-correct for simple-literal-vs-explicit-``xsd:string`` (see module
    docstring): a plain ``Literal("x")`` and ``Literal("x", datatype=XSD.string)``
    compare equal here, unlike in plain ``rdflib.compare.isomorphic``.

    Datasets (``Dataset``, ``ConjunctiveGraph``, ``StarLayerDataset``) are
    compared as datasets: equal canonical N-Quads (RDFC-1.0), so graph names
    count. A dataset and a plain graph are compared as the dataset's quads
    against the graph's triples (default graph only)."""
    if _is_quad_store(graph1) or _is_quad_store(graph2):
        return _canonical_nquads_of(graph1) == _canonical_nquads_of(graph2)
    return _rdflib_isomorphic(_decompose(graph1), _decompose(graph2))


def graph_diff(g1: Any, g2: Any):
    """RDF-1.2-aware replacement for ``rdflib.compare.graph_diff``.

    Operates on (and returns) the *decomposed* graphs - the returned
    "in first only"/"in second only" graphs describe differences in terms of
    the synthetic reification fragments, not the original triple terms, so
    this is meant for programmatic use (e.g. ``len(in_first) == 0``), not for
    display back to a user.

    Raises:
        TypeError: for a dataset (a diff of named graphs is not defined
            here; use ``isomorphic()`` or ``rdfc.to_canonical_nquads``).
    """
    _reject_dataset(g1, g2)
    return _rdflib_graph_diff(_decompose(g1), _decompose(g2))


def to_isomorphic(graph: Any):
    """RDF-1.2-aware replacement for ``rdflib.compare.to_isomorphic`` -
    doesn't crash on a triple-term-valued term. Returns an
    ``IsomorphicGraph`` over the *decomposed* graph (see module docstring);
    use ``to_canonical_hash()`` if you just want a single digest value.

    Raises:
        TypeError: for a dataset (use ``rdfc.to_canonical_nquads``)."""
    _reject_dataset(graph)
    return _rdflib_to_isomorphic(_decompose(graph))


def to_canonical_hash(graph: Any) -> int:
    """A single canonical digest for ``graph``, stable under blank-node
    relabeling and correct for triple terms (including nested blank nodes).

    Not yet a spec-compliant RDFC-1.0 digest (see module docstring) - two
    graphs get equal digests here if and only if ``isomorphic()`` (this
    module's version) says they're isomorphic, which is the property this
    is actually needed for today; ``rdfc.rdfc10_hash`` is the portable,
    standards-compliant digest. For a dataset the digest is the RDFC-1.0
    hash read as an integer.
    """
    if _is_quad_store(graph):
        from starlayer.graph.rdfc import rdfc10_hash

        return int(rdfc10_hash(graph), 16)
    return _rdflib_to_isomorphic(_decompose(graph)).graph_digest()
