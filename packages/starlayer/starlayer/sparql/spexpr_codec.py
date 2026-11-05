"""starlayer.sparql.spexpr_codec

The generic term / expression / property-path / list codec between rdflib's SPARQL algebra nodes
(``CompValue`` / ``Expr``) and RDF. It belongs to the shared ``spexpr:`` vocabulary, not to the ``salg:`` export:
``sqe`` and ``srl`` encode and decode expressions with it, and the ``salg`` export (``to_rdf.py``, ``from_rdf.py``)
imports it, never the other way round. Moved verbatim out of those two files (``docs/working/salg-retirement-analysis.md``,
step 1); the per-call hooks ``_NS_OVERRIDES``, ``_ENCODE_HOOK`` and ``_DECODE_HOOK`` stay context variables.

Encoding half first (was ``to_rdf.py``), decoding half after it (was ``from_rdf.py``); the decoder's own notes follow.
"""

from __future__ import annotations

from contextvars import ContextVar

# ---- decoding half: imports
from pyparsing import ParserElement  # noqa: E402
from rdflib import BNode, Graph, Literal, Namespace, URIRef, Variable
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
from rdflib.plugins.sparql.parserutils import CompValue, Expr

from .vocab import (
    PY_STR_DATATYPE,
    QUERY,
    QUERY_COLLECTION,
    SALG,
    SPEXPR,
    SQE,
    UPDATE,
    UPDATE_OPERATION,
    VARIABLE_DATATYPE,
)

# Lazily initialized cache for _expr_comp_value_names() below.
_EXPR_COMP_VALUE_NAMES: frozenset | None = None


def _expr_comp_value_names() -> frozenset:
    """The real, grammar-verified set of CompValue names that live under
    spexpr: rather than salg: (see vocab.py's own SPEXPR definition for the
    full rationale).

    Lazily imported and cached, not resolved at module top level, to avoid
    a real circular-import risk: this file is itself imported by
    starlayer.sparql's own top-level __init__.py, and expr_families.py
    is imported lazily for the same reason as everything that pulls in
    starontology - a path this project's own
    established "lazy, not top-level" convention exists specifically to
    avoid (see starontology/__init__.py's identical reasoning). Safe to
    defer: nothing can call _encode_comp_value() before starlayer.sparql
    itself has finished importing.

    Returns:
        The frozenset of spexpr:-bound CompValue names.
    """
    global _EXPR_COMP_VALUE_NAMES
    if _EXPR_COMP_VALUE_NAMES is None:
        from .expr_families import _EXPR_NODE_FAMILY

        # TrueFilter is the one spexpr:-bound CompValue name with no entry
        # in _EXPR_NODE_FAMILY (it has no fields of its own to generate a
        # per-builtin shape for - see from_rdf._decode_comp_value's own
        # TrueFilter special case) - added explicitly, not silently
        # missing from the reused table.
        _EXPR_COMP_VALUE_NAMES = frozenset(_EXPR_NODE_FAMILY) | {"TrueFilter"}
    return _EXPR_COMP_VALUE_NAMES


# Per-call namespace overrides for specific CompValue names. sqe's encoder
# sets {"TripleTerm": SQE} while encoding so a triple term inside a query tree
# is an sqe: node, not a salg: one. A ContextVar, not a parameter, because the
# encoder recurses generically through many layers.
_NS_OVERRIDES: ContextVar[dict | None] = ContextVar("_NS_OVERRIDES", default=None)

# Optional per-call encoding hook: ``hook(value, graph)`` returns an RDF node to
# use instead of the generic encoding, or ``NotImplemented`` to fall through.
# sqe uses it to give EXISTS blocks a native where-list encoding.
_ENCODE_HOOK: ContextVar = ContextVar("_ENCODE_HOOK", default=None)


def _comp_value_ns(name: str) -> Namespace:
    """Which namespace a given CompValue.name encodes under - spexpr: for
    the expression-family names that moved out of salg: (2026-10-10), salg:
    for every other algebra operator (Join/Filter/Project/etc. - salg:'s
    own, unmoved vocabulary)."""
    override = (_NS_OVERRIDES.get() or {}).get(name)
    if override is not None:
        return override
    return SPEXPR if name in _expr_comp_value_names() else SALG

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


def _new_tree_graph() -> Graph:
    """The scratch graph the encoders write into when they were not given one: a plain ``rdflib.Graph``. The encoded trees hold
    no RDF 1.2 triple term (a triple term is written as ``sqe:TripleTerm`` structure, a base direction as an encoded datatype),
    so rdflib can hold them; the public entry points convert the result to an ``StarLayerGraph`` (``ox_result``) when they return it."""
    return Graph()


def _encode(value, graph: Graph):
    """Encode one algebra-tree value; return the RDF term/node representing it."""
    if value is None:
        return None

    hook = _ENCODE_HOOK.get()
    if hook is not None and isinstance(value, CompValue):
        hooked = hook(value, graph)
        if hooked is not NotImplemented:
            return hooked

    if isinstance(value, Variable):
        return Literal(str(value), datatype=VARIABLE_DATATYPE)

    if isinstance(value, _LEAF_TERM_TYPES):
        return value

    if isinstance(value, CompValue):  # Expr subclasses CompValue, handled the same way
        # This is also the confirmed mechanism relied on by Phase 6's
        # TripleTermNode (starlayer.sparql.triple_term) — a CompValue
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
            # the same subject/predicate/object shape as starlayer.graph's
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
        f"starlayer.sparql: no RDF encoding yet for algebra value of type "
        f"{type(value).__name__!r}: {value!r} — property paths and some "
        f"advanced operators are out of scope for the current phase, see README"
    )


def _encode_comp_value(node: CompValue, graph: Graph) -> BNode:
    subj = BNode()
    ns = _comp_value_ns(node.name)
    graph.add((subj, RDF.type, ns[node.name]))
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
            # Update-only (quads-by-graph maps never appear on an
            # expression-family node) - always salg:, never spexpr:.
            graph.add((subj, SALG[key], _encode_quads_map(value, graph)))
            continue
        encoded = _encode(value, graph)
        if encoded is None:
            continue
        graph.add((subj, ns[key], encoded))
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
    MulPath/NegatedPath) — see vocab.py's "Property paths" section.

    Each class's own constructor arguments map 1:1 to spexpr: predicates,
    the same "mirror the real shape" rule as the generic CompValue
    encoder, just applied to a Python class hierarchy that isn't a
    CompValue. spexpr:, not salg: (2026-10-10) - Path is one of the
    vocabularies that moved, unconditionally (never ambiguous the way a
    generic CompValue name can be - a Path value is always a Path).

    Args:
        path: The property path to encode.
        graph: The graph to add the encoding triples to.

    Returns:
        The BNode representing the encoded path.
    """
    subj = BNode()
    if isinstance(path, InvPath):
        graph.add((subj, RDF.type, SPEXPR.InvPath))
        graph.add((subj, SPEXPR.arg, _encode(path.arg, graph)))
    elif isinstance(path, SequencePath):
        graph.add((subj, RDF.type, SPEXPR.SequencePath))
        graph.add((subj, SPEXPR.args, _encode_list(path.args, graph)))
    elif isinstance(path, AlternativePath):
        graph.add((subj, RDF.type, SPEXPR.AlternativePath))
        graph.add((subj, SPEXPR.args, _encode_list(path.args, graph)))
    elif isinstance(path, MulPath):
        graph.add((subj, RDF.type, SPEXPR.MulPath))
        graph.add((subj, SPEXPR.path, _encode(path.path, graph)))
        graph.add((subj, SPEXPR.mod, Literal(path.mod)))
    elif isinstance(path, NegatedPath):
        graph.add((subj, RDF.type, SPEXPR.NegatedPath))
        graph.add((subj, SPEXPR.args, _encode_list(path.args, graph)))
    else:
        raise NotImplementedError(
            f"starlayer.sparql: no RDF encoding yet for path type {type(path).__name__!r}"
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
    ?var``). This is a genuine bug in **plain, unmodified rdflib itself**,
    not a gap in this project's own encoding: ``algebra.translate``
    produces ``Extend(var=None)``/``Group.expr=[None, ...]`` for this
    legal-per-grammar construct, which then crashes rdflib's own
    ``evalAggregateJoin`` — see the sibling ``starlayer.graph`` package's
    ``docs/graph/rdflib-upstream-issues.md`` Issue 5 for the full repro,
    and its own
    ``starlayer.graph/query/evaluate_patches.py::patch_group_by_unaliased_expression_key``
    for the actual fix (a parse-tree pre-processing patch, applied
    automatically the moment ``starlayer.graph`` is imported — which every real
    usage of this project already does, since it needs a backend to
    execute against). Once that patch is active, ``algebra.translate``
    itself never produces the broken ``[None]`` shape in the first place,
    so this function never sees it — this check only still fires if
    ``starlayer.sparql`` is used standalone, with `starlayer.graph` never
    imported at all.
    """
    encoded_items = [_encode(item, graph) for item in items]
    if any(encoded is None for encoded in encoded_items):
        # _encode(v) returns bare None only when v itself is None (every
        # other branch either returns a real term/node or raises) - so
        # this is unambiguously the case documented above, not a generic
        # "something failed silently" situation.
        raise NotImplementedError(
            "starlayer.sparql: cannot encode a GROUP BY clause using an "
            "un-aliased, expression-valued grouping key (e.g. `GROUP BY "
            "(?o+1)` with no `AS ?var`) — confirmed this is not a gap in "
            "this project's own encoding, but a genuine bug in plain, "
            "unmodified rdflib itself (see the sibling starlayer.graph "
            "repo's docs/upstream-issues/rdflib-upstream-issues.md Issue 9). This is "
            "already fixed transparently if `starlayer.graph` has been "
            "imported (`import starlayer.graph` applies "
            "patch_group_by_unaliased_expression_key at import time) — "
            "if you're seeing this, starlayer.sparql is being used "
            "without starlayer.graph ever imported. Either import "
            "starlayer.graph first, or add an explicit `AS ?var` alias to the "
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

    Args:
        row: One VALUES-clause binding row (variable -> bound value, or
            the "UNDEF" sentinel string).
        graph: The graph to add the encoding triples to.

    Returns:
        The ``rdf:List`` node (or ``rdf:nil`` if ``row`` is empty) encoding
        this row.
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


# ---- decoding half
# Optional per-call decoding hook: ``hook(node, graph)`` returns the decoded
# value, or ``NotImplemented`` to fall through (see to_rdf._ENCODE_HOOK).
_DECODE_HOOK: ContextVar = ContextVar("_DECODE_HOOK", default=None)

_SALG_NS = str(SALG)
_SQE_NS = str(SQE)
_SPEXPR_NS = str(SPEXPR)


def _strip_vocab_ns(uri: str) -> str | None:
    """The bare local name of ``uri``, stripping whichever of salg:/spexpr:'s
    namespace prefix it actually starts with.

    Both namespaces need recognizing here (2026-10-10): real encoded data
    from before the spexpr: split still has salg:-typed expression/path/
    variable nodes, and this decoder has to keep reading those exactly as
    it always did, while new data types the same values under spexpr:
    instead - see vocab.py's SPEXPR definition for the full rationale.

    Args:
        uri: The full URI string to strip.

    Returns:
        The bare local name, or ``None`` if ``uri`` starts with neither
        namespace.
    """
    if uri.startswith(_SPEXPR_NS):
        return uri[len(_SPEXPR_NS):]
    if uri.startswith(_SALG_NS):
        return uri[len(_SALG_NS):]
    if uri.startswith(_SQE_NS):
        return uri[len(_SQE_NS):]
    return None

# (node name, key) pairs whose value must decode to a genuine Python
# int/bool, not merely an rdflib Literal that happens to compare equal to
# one — Slice.start/.length are passed straight to itertools.islice, which
# requires a real int; a boolean Literal is always truthy in a plain Python
# `if` regardless of its actual value, since it's a non-empty string either
# way. See vocab.py's "Bare Python strings" section for the str case, which
# — unlike int/bool — is handled generically rather than by listing keys
# here.
#
# Scoped by (node name, key) pair, not key name alone: `start`/`length` are
# also `Builtin_SUBSTR`'s own parameter names (SPARQL's `SUBSTR(str, start[,
# length])`), a completely unrelated node where they must stay real
# `Literal`s — `operators.Builtin_SUBSTR` calls `numeric(expr.start)`,
# which raises `SPARQLTypeError` for anything that isn't a `Literal`
# instance. A bare key-name match would convert `Builtin_SUBSTR`'s own
# `start`/`length` to plain ints too, and `evalExtend` silently swallows
# that error into "leave the BIND target unbound" rather than raising — so
# a decoded `BIND(SUBSTR(...) AS ?z)` would look like it worked (no
# exception) while silently never binding `?z`.
_PLAIN_VALUE_KEYS = {("Slice", "start"), ("Slice", "length"), ("Join", "lazy")}


def _discover_expr_evalfns() -> dict:
    import rdflib.plugins.sparql.parser as parser_module
    from rdflib.plugins.sparql.parserutils import Comp

    registry: dict = {}
    visited: set = set()

    def walk(e: ParserElement) -> None:
        if id(e) in visited:
            return
        visited.add(id(e))
        if isinstance(e, Comp) and getattr(e, "evalfn", None) is not None:
            registry.setdefault(e.name, e.evalfn)
        for attr in ("expr", "exprs"):
            sub = getattr(e, attr, None)
            if isinstance(sub, ParserElement):
                walk(sub)
            elif isinstance(sub, (list, tuple)):
                for s in sub:
                    if isinstance(s, ParserElement):
                        walk(s)

    for value in vars(parser_module).values():
        if isinstance(value, ParserElement):
            walk(value)
    return registry


_EXPR_EVALFNS = _discover_expr_evalfns()


def _decode(node, graph: Graph):
    if node is None:
        return None

    hook = _DECODE_HOOK.get()
    if hook is not None and isinstance(node, BNode):
        hooked = hook(node, graph)
        if hooked is not NotImplemented:
            return hooked

    if isinstance(node, Literal):
        if node.datatype == VARIABLE_DATATYPE:
            return Variable(str(node))
        if node.datatype == PY_STR_DATATYPE:
            return str(node)
        return node

    if isinstance(node, URIRef):
        return node

    if isinstance(node, BNode):
        if (node, RDF.type, SALG.TriplePattern) in graph:
            return _decode_triple_pattern(node, graph)
        if (node, RDF.first, None) in graph:
            first_item = graph.value(node, RDF.first)
            if (first_item, RDF.type, SALG.Binding) in graph:
                return _decode_binding_row(node, graph)
            return _decode_list(node, graph)
        comp_type = _comp_value_type(node, graph)
        if comp_type is not None:
            local_name = _strip_vocab_ns(str(comp_type))
            if local_name in _PATH_TYPE_NAMES:
                return _decode_path(node, local_name, graph)
            return _decode_comp_value(node, comp_type, graph)
        return node  # a plain blank node used directly as a query term

    raise NotImplementedError(
        f"starlayer.sparql: cannot decode node {node!r} of type {type(node).__name__}"
    )


# (CompValue name, key) pairs whose value is genuinely a Python *list* in
# rdflib's own algebra — the only fields where a bare `rdf:nil` (an empty
# RDF List's own terminator, indistinguishable at the RDF level from an
# ordinary term whose *value* happens to be rdf:nil — e.g. an ordinary
# triple pattern `?s ?p rdf:nil`, a common RDF-List-processing idiom)
# should decode to `[]` rather than the literal `rdf:nil` URIRef. Getting
# this wrong in either direction is real damage: treating a genuinely
# list-valued field's empty `rdf:nil` as a literal term instead of `[]`
# crashes `algebra.reorderTriples`/`_knownTerms` (a raw Python list is
# unhashable, and `BGP.triples` elements must be hashable) or silently
# produces wrong results; treating an *ordinary* term's `rdf:nil` as `[]`
# instead loses that term outright (e.g. a triple pattern's object).
#
# Empirically derived (not guessed) by instrumenting
# to_rdf._encode_comp_value and running it over (a) every real .rq
# fixture in this repo's own test suites (W3C SPARQL 1.1/1.2 conformance +
# this project's own) — 198 successfully-parsed fixtures, covering every
# query-side operator this project's own conformance tests exercise — and
# (b) a hand-built battery covering every SPARQL Update operation form
# (InsertData/DeleteData/DeleteWhere/Modify's delete+insert clauses/Load/
# Clear/Drop/Create/Add/Move/Copy), since the .rq corpus in (a)
# under-represents Update text. The Add/Move/Copy "graph" entries are the
# (source, destination) 2-tuple `to_rdf.py` itself notes is "no special
# shape of its own, just an ordered sequence" - genuinely a list at the
# RDF level even though never realistically empty.
_LIST_VALUED_KEYS = {
    ("Add", "graph"),
    ("Aggregate_Avg", "distinct"),
    ("Aggregate_Count", "distinct"),
    ("Aggregate_GroupConcat", "distinct"),
    ("Aggregate_Max", "distinct"),
    ("Aggregate_Min", "distinct"),
    ("Aggregate_Sample", "distinct"),
    ("Aggregate_Sum", "distinct"),
    ("BGP", "triples"),
    ("ConditionalAndExpression", "other"),
    ("ConstructQuery", "template"),
    ("Copy", "graph"),
    ("DeleteClause", "triples"),
    ("DeleteData", "triples"),
    ("DeleteWhere", "triples"),
    ("Function", "distinct"),
    ("InsertClause", "triples"),
    ("InsertData", "triples"),
    ("Move", "graph"),
    ("OrderBy", "expr"),
    ("Project", "PV"),
    ("SelectQuery", "PV"),
    ("values", "res"),
}
# The eight `("...", "distinct")` entries above are exhaustive, not a
# sample: confirmed by grepping rdflib's own parser.py for every
# `Param("distinct", ...)` (all 8 Aggregate_*/Function ArgList productions
# use the *same* `_Distinct = Optional(Keyword("DISTINCT"))` grammar rule,
# which pyparsing represents as an empty ParseResults - encoded as an empty
# Python list - whenever DISTINCT is absent, the overwhelmingly common
# case) - no other CompValue field in rdflib's whole SPARQL 1.1 grammar
# uses this exact "Optional keyword with no explicit non-list default"
# pattern (grepped for `Param("<name>", Optional(...))` generally, not just
# "distinct" - zero other matches), and starlayer.sparql's own SPARQL 1.2 grammar
# extensions (grammar12.py) don't introduce a new instance of it either.

# RelationalExpression.other is deliberately NOT in _LIST_VALUED_KEYS above -
# it's genuinely polymorphic, not a fixed list-or-term choice per key. Per
# the SPARQL grammar itself (rdflib parser.py's own comment: "[114]
# RelationalExpression ::= NumericExpression ( '=' NumericExpression | ... |
# 'IN' ExpressionList | 'NOT' 'IN' ExpressionList )?"), `other` is a list
# only for the IN/NOT IN forms (an ExpressionList) - an ordinary single
# NumericExpression for every other operator (=, !=, <, >, <=, >=). A static
# per-key classification can't express "depends on this same node's other
# own field" - handled instead in _decode_comp_value by checking the node's
# own salg:op value directly. A non-empty list already round-trips correctly
# either way via the ordinary rdf:first-based structural list detection in
# _decode() - this only matters for a bare rdf:nil, i.e. IN ()'s empty list
# vs. an ordinary comparison's operand genuinely being the term rdf:nil.


def _decode_list_field(node, graph: Graph):
    """Decode a value known (via context, not guessed) to be list-valued —
    unlike plain `_decode()`, a bare `rdf:nil` here correctly means the
    empty list, not the literal term."""
    if node == RDF.nil:
        return []
    return _decode(node, graph)


_PATH_TYPE_NAMES = {"InvPath", "SequencePath", "AlternativePath", "MulPath", "NegatedPath"}


def _decode_path(node: BNode, local_name: str, graph: Graph) -> Path:
    """Inverse of to_rdf._encode_path — see vocab.py's "Property paths"
    section for why these need dedicated handling (rdflib.paths.Path
    objects, not CompValue). spexpr:, not salg: (2026-10-10) - see
    _encode_path's own matching note.

    Args:
        node: The encoded path's root node.
        local_name: The path's CompValue-style type name (e.g.
            "SequencePath"), already stripped of its namespace.
        graph: The graph holding the encoded path.

    Returns:
        The reconstructed ``rdflib.paths.Path`` instance.
    """
    if local_name == "InvPath":
        return InvPath(_decode(graph.value(node, SPEXPR.arg), graph))
    if local_name == "SequencePath":
        return SequencePath(*_decode_list_field(graph.value(node, SPEXPR.args), graph))
    if local_name == "AlternativePath":
        return AlternativePath(*_decode_list_field(graph.value(node, SPEXPR.args), graph))
    if local_name == "MulPath":
        path = _decode(graph.value(node, SPEXPR.path), graph)
        mod = str(graph.value(node, SPEXPR.mod))
        return MulPath(path, mod)
    if local_name == "NegatedPath":
        # NegatedPath.__init__ takes one arg (a URIRef/InvPath/AlternativePath)
        # and expands it into self.args itself — it doesn't accept an
        # already-expanded list, so build the instance directly and set
        # .args, matching exactly what __init__ would have produced. Safe:
        # Path.eval/.n3/__repr__ only ever read .args, never re-derive it.
        obj = object.__new__(NegatedPath)
        obj.args = _decode_list_field(graph.value(node, SPEXPR.args), graph)
        return obj
    raise NotImplementedError(f"starlayer.sparql: no decoder for path type {local_name!r}")


# Reserved key names _encode_prologue (to_rdf.py) writes directly onto a
# query/update root node — see _decode_comp_value's use of this below.
_PROLOGUE_KEYS = {"base", "prologuePrefix"}

_AUXILIARY_ROOT_MARKERS = {QUERY, UPDATE, UPDATE_OPERATION, QUERY_COLLECTION}


def _comp_value_type(node: BNode, graph: Graph) -> URIRef | None:
    """The real CompValue-style ``rdf:type`` for ``node`` — a salg:/spexpr:
    type, distinguished from the auxiliary root-marker types ``to_rdf.py``
    layers onto a query/update root alongside its real CompValue type.

    Args:
        node: The node to inspect.
        graph: The graph holding ``node``.

    Returns:
        The node's real CompValue type URI, or ``None`` if it has no
        salg:/spexpr: type at all.
    """
    types = [t for t in graph.objects(node, RDF.type) if _strip_vocab_ns(str(t)) is not None]
    if not types:
        return None
    # SALG.Query/UPDATE/UPDATE_OPERATION are auxiliary index markers (see
    # to_rdf.query_to_rdf / update_to_rdf), added alongside the node's real
    # CompValue type (e.g. SelectQuery, InsertData) — never a real CompValue
    # name on their own, so they lose to any other salg: type present on the
    # same node.
    specific = [t for t in types if t not in _AUXILIARY_ROOT_MARKERS]
    return (specific or types)[0]


def _decode_triple_pattern(node, graph: Graph) -> tuple:
    s = _decode(graph.value(node, SALG.subject), graph)
    p = _decode(graph.value(node, SALG.predicate), graph)
    o = _decode(graph.value(node, SALG.object), graph)
    return (s, p, o)


def _decode_list(node, graph: Graph) -> list:
    return [_decode(item, graph) for item in Collection(graph, node)]


def _decode_binding_row(node, graph: Graph) -> dict:
    """Inverse of to_rdf._encode_binding_row: an rdf:List of salg:Binding
    nodes -> a Values.res row. No UNDEF special-casing needed — the generic
    bare-str decoding above already reconstructs the exact "UNDEF" sentinel
    rdflib's evaluator expects, distinctly from a real Literal("UNDEF")."""
    row: dict = {}
    for binding in Collection(graph, node):
        var = _decode(graph.value(binding, SALG.var), graph)
        row[var] = _decode(graph.value(binding, SALG.val), graph)
    return row


def _decode_quads_map(node, graph: Graph) -> dict:
    """Inverse of to_rdf._encode_quads_map — see vocab.py's "Update
    quads-by-graph maps" section. Rebuilt as a defaultdict(list), matching
    algebra.translateQuads's own return type."""
    from collections import defaultdict

    result: dict = defaultdict(list)
    if node == RDF.nil:
        return result
    for qnode in Collection(graph, node):
        graph_term = _decode(graph.value(qnode, SALG.graph), graph)
        result[graph_term] = _decode_list_field(graph.value(qnode, SALG.triples), graph)
    return result


def _to_python_deep(value):
    """Recursively unwrap rdflib Literal -> plain Python, for keys in
    _PLAIN_VALUE_KEYS (whose original value may itself be a list, e.g.
    AdditiveExpression/MultiplicativeExpression's "op" is a list of operator
    strings, one per element of "other")."""
    if isinstance(value, Literal):
        return value.toPython()
    if isinstance(value, list):
        return [_to_python_deep(v) for v in value]
    return value


def _decode_comp_value(node, type_uri: URIRef, graph: Graph):
    name = _strip_vocab_ns(str(type_uri))
    kwargs: dict = {}
    for pred, obj in graph.predicate_objects(node):
        if pred == RDF.type:
            continue
        key = _strip_vocab_ns(str(pred))
        if key is None:
            continue
        if key in _PROLOGUE_KEYS:
            # _encode_prologue attaches these directly to the algebra/update
            # root node (see to_rdf.py) so they're queryable without an
            # extra hop — but that root is also a real CompValue (e.g.
            # SelectQuery) or, for an Update, the dedicated container node.
            # No real CompValue anywhere uses these key names, but the
            # generic predicate scan above can't tell "real CompValue key"
            # apart from "prologue metadata sharing this node" on its own -
            # reconstructed separately via _decode_prologue, so skipped here
            # rather than polluting the CompValue's own keys.
            continue
        if key == "quads":
            kwargs[key] = _decode_quads_map(obj, graph)
            continue
        if (name, key) in _LIST_VALUED_KEYS or (
            name == "RelationalExpression"
            and key == "other"
            and str(graph.value(node, SPEXPR.op)) in ("IN", "NOT IN")
        ):
            value = _decode_list_field(obj, graph)
        else:
            value = _decode(obj, graph)
        if (name, key) in _PLAIN_VALUE_KEYS:
            value = _to_python_deep(value)
        kwargs[key] = value

    if name == "values" and isinstance(kwargs.get("res"), list):
        # A VALUES row with no variables (``VALUES () { () }``) is encoded as
        # an empty RDF list, which decodes to rdf:nil; the row is ``{}``.
        kwargs["res"] = [{} if row == RDF.nil else row for row in kwargs["res"]]

    if name == "TrueFilter":
        # The module-level singleton Expr rdflib's own algebra uses for a
        # filter-less OPTIONAL's LeftJoin.expr — see algebra.py's
        # translateGroupGraphPattern. Has no keys of its own; reuse the real
        # singleton rather than reconstructing an equivalent Expr, since some
        # rdflib code may compare against it by identity.
        from rdflib.plugins.sparql.operators import TrueFilter

        return TrueFilter

    if name == "TripleTerm":
        # Must be reconstructed as TripleTermNode (a CompValue subclass with
        # __hash__/__eq__/__lt__ bolted on), not a bare CompValue — a bare
        # CompValue sitting inside a BGP.triples tuple crashes
        # algebra.reorderTriples/_knownTerms (unhashable), which rdf_to_query
        # runs (via the _addVars/analyse bookkeeping recompute below) on
        # every decode. See starlayer.sparql.triple_term for why.
        from .triple_term import TripleTermNode

        result_tt = TripleTermNode(name)
        result_tt.update(kwargs)
        # A malformed salg:TripleTerm graph (hand-authored, LLM-authored, or
        # otherwise not produced by this project's own to_rdf.py) could
        # encode a nested triple term in subject/predicate position just as
        # easily as SPARQL 1.2 text can — see InvalidTripleTermError for why
        # this must be rejected regardless of construction path.
        return result_tt.validate()

    evalfn = _EXPR_EVALFNS.get(name)
    if evalfn is not None:
        result = Expr(name, evalfn)
        result.update(kwargs)
        if name in ("Builtin_EXISTS", "Builtin_NOTEXISTS") and "graph" in kwargs:
            # rdflib's own operators.Builtin_EXISTS/_NOTEXISTS read `.graph`
            # via plain attribute syntax (`e.graph`), not `e["graph"]` -
            # deliberately, since a real instance attribute bypasses
            # CompValue's ctx-based value-resolution (`__getattr__` is only
            # ever consulted when normal attribute lookup fails). That
            # resolution path cannot handle a raw, non-Expr graph-pattern
            # node - it only knows how to evaluate an Expr or look up an RDF
            # term - and `.graph` is exactly that: a raw parse-tree/algebra
            # fragment, not an expression. rdflib's own
            # algebra.translateExists sets `.graph` as a real instance
            # attribute for exactly this reason; a plain
            # `result.update(kwargs)` here only stores it as a dict key, so
            # evaluating a decoded EXISTS/NOT EXISTS node whose `.graph` is
            # more than a single triple crashes ("What do I do with this
            # CompValue?"). Mirror translateExists exactly.
            result.graph = kwargs["graph"]
        return result

    return CompValue(name, **kwargs)
