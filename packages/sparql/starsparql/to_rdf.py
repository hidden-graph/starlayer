"""Encode a SPARQL algebra tree (rdflib CompValue/Expr nodes) as RDF triples.

One generic recursive walker handles every algebra operator and every
expression builtin uniformly — see ``vocab.py``'s module docstring for why
that is the design (and not one function per operator name).
"""

from __future__ import annotations

from rdflib import BNode, Graph, Literal, URIRef, Variable
from rdflib.collection import Collection
from rdflib.namespace import RDF
from rdflib.paths import (
    AlternativePath,
    InvPath,
    MulPath,
    NegatedPath,
    Path,
    SequencePath,
)
from rdflib.plugins.sparql.parserutils import CompValue
from rdflib.plugins.sparql.sparql import Prologue, Query, Update

from .vocab import (
    PY_STR_DATATYPE,
    QUERY,
    QUERY_COLLECTION,
    SALG,
    UPDATE,
    UPDATE_OPERATION,
    VARIABLE_DATATYPE,
)

_LEAF_TERM_TYPES = (URIRef, BNode, Literal)
_PRIMITIVE_TYPES = (str, int, float, bool)

# Bookkeeping keys rdflib's own translateQuery() stamps onto every algebra
# node *after* building it, purely as a query-planning cache derived from
# the tree's own structure (which variables a subtree binds, whether a Join
# can be evaluated lazily) — see algebra.py's _addVars/analyse, run via
# _traverseAgg at the tail of translateQuery. Not real SPARQL algebra, so
# not part of this vocabulary: skipped here, and recomputed the same way
# rdflib itself computes them after from_rdf.rdf_to_query decodes a tree.
_INTERNAL_BOOKKEEPING_KEYS = {"_vars", "lazy"}

# A CompValue key whose value, wherever it appears, is a graph-term-keyed
# map of triples rather than an ordinary nested algebra value — see vocab.py's
# "Update quads-by-graph maps" section.
_QUADS_KEY = "quads"


def _new_starlayer_graph() -> Graph:
    """The default graph for any encoding function below that wasn't given
    one — always a real ``starlayergraph.graph.starlayer_graph.StarLayerGraph``,
    never a plain ``rdflib.Graph``. Raises ``ImportError`` — not a silent
    fallback — if ``starlayergraph`` isn't installed: a plain ``Graph``
    can't correctly round-trip a dirLangString literal's real
    ``"text"@lang--dir`` syntax on serialization (it would only ever see
    starlayergraph's own internal ``dirlang:`` datatype encoding as an opaque
    IRI), and isn't a real RDF 1.2 graph for storage/reference purposes.
    This project hard-requires ``starlayergraph`` rather than degrading to
    a lesser default — a caller that genuinely doesn't need either property
    can still pass its own plain ``rdflib.Graph()`` explicitly via the
    ``graph`` parameter; this default is deliberately not that permissive.
    """
    from starlayergraph.graph.starlayer_graph import StarLayerGraph

    return StarLayerGraph()


def query_to_rdf(query: Query, graph: Graph | None = None) -> tuple[Graph, BNode]:
    """Encode a prepared rdflib ``Query`` (from ``prepareQuery``/``translateQuery``,
    starlayergraph's SPARQL-1.2-aware variants included) as RDF triples.

    Returns ``(graph, root)`` — ``graph`` is ``graph`` if given, else a fresh
    ``StarLayerGraph`` (see ``_new_starlayer_graph``); ``root`` is the node
    for ``query.algebra``, additionally typed ``salg:Query`` (see
    ``vocab.QUERY``) so encoded queries in a larger store can always be
    found via ``?q a salg:Query`` regardless of query form.
    """
    if graph is None:
        graph = _new_starlayer_graph()
    root = _encode(query.algebra, graph)
    graph.add((root, RDF.type, QUERY))
    _encode_prologue(query.prologue, root, graph)
    return graph, root


def update_to_rdf(update: Update, graph: Graph | None = None) -> tuple[Graph, BNode]:
    """Encode a prepared rdflib ``Update`` (from ``prepareUpdate``/
    ``translateUpdate``) as RDF triples.

    ``update.algebra`` is a ``List[CompValue]`` — one operation per
    semicolon-separated request in the Update string, executed in that
    order. ``root`` is a dedicated container node (not itself a CompValue,
    typed ``salg:Update`` — see ``vocab.UPDATE``) holding ``salg:operations``
    (an ``rdf:List`` of the encoded operations — order matters and must
    survive the round-trip) plus the request's shared Prologue
    (``salg:base``/``salg:prologuePrefix`` — SPARQL Update has one Prologue
    per request, not one per operation, unlike a Query). Each operation node
    is additionally typed ``salg:UpdateOperation`` (see
    ``vocab.UPDATE_OPERATION``).
    """
    if graph is None:
        graph = _new_starlayer_graph()
    op_nodes = []
    for op in update.algebra:
        node = _encode(op, graph)
        graph.add((node, RDF.type, UPDATE_OPERATION))
        op_nodes.append(node)
    root = BNode()
    graph.add((root, RDF.type, UPDATE))
    graph.add((root, SALG.operations, _build_rdf_list(op_nodes, graph)))
    _encode_prologue(update.prologue, root, graph)
    return graph, root


def queries_to_collection(queries: list[Query], graph: Graph | None = None) -> tuple[Graph, BNode]:
    """Encode a list of independent, prepared rdflib ``Query`` objects as one
    RDF ``salg:QueryCollection`` — the collection-of-independent-queries
    counterpart of ``update_to_rdf``'s single-request ``salg:operations``
    list (see ``vocab.QUERY_COLLECTION``). Unlike an Update's operations,
    which share one Prologue across the whole request, each query keeps its
    own — ``query_to_rdf`` already encodes it per query, so nothing extra is
    needed here for that.

    Returns ``(graph, root)`` — ``graph`` is ``graph`` if given, else a
    fresh ``StarLayerGraph`` (see ``_new_starlayer_graph``); ``root`` is a
    dedicated container node holding ``salg:queries`` (an ``rdf:List`` of
    the member queries' own ``salg:Query``-typed roots, in the order given —
    order isn't semantically meaningful for a collection, but is preserved
    anyway since ``rdf:List`` is ordered regardless).
    """
    if graph is None:
        graph = _new_starlayer_graph()
    query_nodes = [query_to_rdf(query, graph)[1] for query in queries]
    root = BNode()
    graph.add((root, RDF.type, QUERY_COLLECTION))
    graph.add((root, SALG.queries, _build_rdf_list(query_nodes, graph)))
    return graph, root


def _encode_prologue(prologue: Prologue | None, root, graph: Graph) -> None:
    """Encode a Query/Update's Prologue (BASE + PREFIX declarations) onto its
    root node — see vocab.py's "Prologue (BASE/PREFIX)" section for why this
    is round-tripped (BASE-relative IRI()/URI() builtin correctness) and what
    it doesn't fix (rdflib's own algebra.translateAlgebra never reads
    prologue, so this can't make regenerated query text use prefixes)."""
    if prologue is None:
        return
    if prologue.base:
        graph.add((root, SALG.base, URIRef(prologue.base)))
    for prefix, namespace in prologue.namespace_manager.namespaces():
        binding = BNode()
        graph.add((binding, RDF.type, SALG.PrefixBinding))
        graph.add((binding, SALG.prefixLabel, _encode(prefix, graph)))
        graph.add((binding, SALG.namespace, URIRef(namespace)))
        graph.add((root, SALG.prologuePrefix, binding))


def _encode(value, graph: Graph):
    """Encode one algebra-tree value; return the RDF term/node representing it."""
    if value is None:
        return None

    if isinstance(value, Variable):
        return Literal(str(value), datatype=VARIABLE_DATATYPE)

    if isinstance(value, _LEAF_TERM_TYPES):
        return value

    if isinstance(value, CompValue):  # Expr subclasses CompValue, handled the same way
        # This is also the confirmed mechanism relied on by Phase 6's
        # TripleTermNode (starsparql.triple_term) — a CompValue
        # subclass, so it needs zero special-casing here: same rd:type
        # salg:TripleTerm + salg:subject/predicate/object shape as any other
        # CompValue, per vocab.py's "Triple terms" section.
        return _encode_comp_value(value, graph)

    if isinstance(value, Path):
        return _encode_path(value, graph)

    if isinstance(value, tuple):
        if len(value) == 3:
            # BGP.triples elements: a plain (s, p, o) tuple, not a CompValue.
            # See vocab.py's "Triple patterns" section for why this reuses
            # the same subject/predicate/object shape as starlayergraph's
            # TripleTerm.
            return _encode_triple_pattern(value, graph)
        # Any other tuple (e.g. Add/Move/Copy's 2-tuple (src, dst) graph
        # pair) — no special shape of its own, just an ordered sequence.
        return _encode_list(list(value), graph)

    if isinstance(value, list):
        return _encode_list(value, graph)

    if isinstance(value, dict):
        # A VALUES clause row: Values.res is a List[Dict[Variable, term]] —
        # see vocab.py's "Binding rows" section.
        return _encode_binding_row(value, graph)

    if type(value) is str:
        # A bare Python str living inside the algebra tree — never a real
        # RDF term at this point (a real one would already have matched
        # _LEAF_TERM_TYPES above). See vocab.py's "Bare Python strings"
        # section for why this needs its own reserved datatype rather than
        # falling into the plain Literal(value) case below.
        return Literal(value, datatype=PY_STR_DATATYPE)

    if isinstance(value, _PRIMITIVE_TYPES):
        return Literal(value)

    raise NotImplementedError(
        f"starsparql: no RDF encoding yet for algebra value of type "
        f"{type(value).__name__!r}: {value!r} — property paths and some "
        f"advanced operators are out of scope for the current phase, see README"
    )


def _encode_comp_value(node: CompValue, graph: Graph) -> BNode:
    subj = BNode()
    graph.add((subj, RDF.type, SALG[node.name]))
    for key, value in node.items():
        if key in _INTERNAL_BOOKKEEPING_KEYS:
            continue
        if key in node.__dict__:
            # See lower_rdf11.py's _lower_expr for the full explanation:
            # rdflib's own translateQuery post-processing (e.g.
            # algebra.translateExists, for Builtin_EXISTS/NOTEXISTS's
            # `graph`) fixes up certain keys via a shadowing instance
            # attribute assignment (`n.graph = ...`) rather than updating
            # the underlying dict-stored value `.items()` just yielded -
            # so `value` here can be a stale, untranslated parse-tree
            # fragment. Prefer the attribute whenever both exist.
            value = getattr(node, key)
        if key == _QUADS_KEY:
            graph.add((subj, SALG[key], _encode_quads_map(value, graph)))
            continue
        encoded = _encode(value, graph)
        if encoded is None:
            continue
        graph.add((subj, SALG[key], encoded))
    return subj


def _encode_quads_map(quads: dict, graph: Graph) -> BNode | URIRef:
    """Encode an Update operation's quads-by-graph map (see vocab.py's
    "Update quads-by-graph maps" section) as an rdf:List of
    salg:QuadsForGraph nodes."""
    nodes = []
    for graph_term, triples_for_graph in quads.items():
        qnode = BNode()
        graph.add((qnode, RDF.type, SALG.QuadsForGraph))
        graph.add((qnode, SALG.graph, _encode(graph_term, graph)))
        graph.add((qnode, SALG.triples, _encode_list(list(triples_for_graph), graph)))
        nodes.append(qnode)
    return _build_rdf_list(nodes, graph)


def _encode_path(path: Path, graph: Graph) -> BNode:
    """Encode an rdflib.paths.Path (InvPath/SequencePath/AlternativePath/
    MulPath/NegatedPath) — see vocab.py's "Property paths" section. Each
    class's own constructor arguments map 1:1 to salg: predicates, the same
    "mirror the real shape" rule as the generic CompValue encoder, just
    applied to a Python class hierarchy that isn't a CompValue."""
    subj = BNode()
    if isinstance(path, InvPath):
        graph.add((subj, RDF.type, SALG.InvPath))
        graph.add((subj, SALG.arg, _encode(path.arg, graph)))
    elif isinstance(path, SequencePath):
        graph.add((subj, RDF.type, SALG.SequencePath))
        graph.add((subj, SALG.args, _encode_list(path.args, graph)))
    elif isinstance(path, AlternativePath):
        graph.add((subj, RDF.type, SALG.AlternativePath))
        graph.add((subj, SALG.args, _encode_list(path.args, graph)))
    elif isinstance(path, MulPath):
        graph.add((subj, RDF.type, SALG.MulPath))
        graph.add((subj, SALG.path, _encode(path.path, graph)))
        graph.add((subj, SALG.mod, Literal(path.mod)))
    elif isinstance(path, NegatedPath):
        graph.add((subj, RDF.type, SALG.NegatedPath))
        graph.add((subj, SALG.args, _encode_list(path.args, graph)))
    else:
        raise NotImplementedError(
            f"starsparql: no RDF encoding yet for path type {type(path).__name__!r}"
        )
    return subj


def _encode_triple_pattern(triple: tuple, graph: Graph) -> BNode:
    s, p, o = triple
    subj = BNode()
    graph.add((subj, RDF.type, SALG.TriplePattern))
    graph.add((subj, SALG.subject, _encode(s, graph)))
    graph.add((subj, SALG.predicate, _encode(p, graph)))
    graph.add((subj, SALG.object, _encode(o, graph)))
    return subj


def _encode_list(items: list, graph: Graph) -> BNode | URIRef:
    """Encode a plain Python list as an ``rdf:List``.

    A bare Python ``None`` as a whole property's *value* means "omit this
    triple" (see ``_encode``/``_encode_comp_value`` above) — but a ``None``
    surviving as one *item inside* this list is a different case, arising
    from exactly one real shape: ``Group.expr`` for an un-aliased,
    expression-valued ``GROUP BY`` key (``GROUP BY (?o+1)``, no ``AS
    ?var``). Confirmed this is not a gap in this project's own encoding but
    a genuine bug in **plain, unmodified rdflib itself**
    (``algebra.translate`` produces ``Extend(var=None)``/
    ``Group.expr=[None, ...]`` for this legal-per-grammar construct, which
    then crashes rdflib's own ``evalAggregateJoin``) — see the sibling
    ``starlayergraph`` repo's ``docs/rdflib-upstream-issues.md`` Issue 9
    for the full trace, and its own
    ``starlayergraph/query/evaluate_patches.py::patch_group_by_unaliased_expression_key``
    for the actual fix (a parse-tree pre-processing patch, applied
    automatically the moment ``starlayergraph`` is imported — which every real
    usage of this project already does, since it needs a backend to
    execute against). Once that patch is active, ``algebra.translate``
    itself never produces the broken ``[None]`` shape in the first place,
    so this function never sees it — this check only still fires if
    ``starsparql`` is used standalone, with `starlayergraph` never
    imported at all.
    """
    encoded_items = [_encode(item, graph) for item in items]
    if any(encoded is None for encoded in encoded_items):
        # _encode(v) returns bare None only when v itself is None (every
        # other branch either returns a real term/node or raises) - so
        # this is unambiguously the case documented above, not a generic
        # "something failed silently" situation.
        raise NotImplementedError(
            "starsparql: cannot encode a GROUP BY clause using an "
            "un-aliased, expression-valued grouping key (e.g. `GROUP BY "
            "(?o+1)` with no `AS ?var`) — confirmed this is not a gap in "
            "this project's own encoding, but a genuine bug in plain, "
            "unmodified rdflib itself (see the sibling starlayergraph "
            "repo's docs/rdflib-upstream-issues.md Issue 9). This is "
            "already fixed transparently if `starlayergraph` has been "
            "imported (`import starlayergraph` applies "
            "patch_group_by_unaliased_expression_key at import time) — "
            "if you're seeing this, starsparql is being used "
            "without starlayergraph ever imported. Either import "
            "starlayergraph first, or add an explicit `AS ?var` alias to the "
            "grouping expression (`GROUP BY (?o+1 AS ?k)`, which works "
            "correctly in plain rdflib too) to work around it."
        )
    return _build_rdf_list(encoded_items, graph)


def _encode_binding_row(row: dict, graph: Graph) -> BNode | URIRef:
    """Encode one VALUES-clause row (one of Values.res's list elements) as
    an rdf:List of salg:Binding nodes. See vocab.py's "Binding rows" section.

    Every variable in a VALUES clause gets a dict entry for every row,
    including an UNDEF one — rdflib represents that not as Python None but
    as the bare *string* "UNDEF" (evalValues in rdflib's own evaluate.py
    checks ``if v != "UNDEF"`` before binding). No special-casing needed
    here for it: the generic bare-str handling in _encode (see vocab.py's
    "Bare Python strings" section) already round-trips that bare string
    faithfully, distinctly from a real Literal("UNDEF") term.
    """
    binding_nodes = []
    for var, val in row.items():
        b = BNode()
        graph.add((b, RDF.type, SALG.Binding))
        graph.add((b, SALG.var, _encode(var, graph)))
        graph.add((b, SALG.val, _encode(val, graph)))
        binding_nodes.append(b)
    return _build_rdf_list(binding_nodes, graph)


def _build_rdf_list(nodes: list, graph: Graph) -> BNode | URIRef:
    if not nodes:
        return RDF.nil
    list_node = BNode()
    Collection(graph, list_node, nodes)
    return list_node
