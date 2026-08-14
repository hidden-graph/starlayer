"""Decode RDF triples (as produced by ``to_rdf.py``) back into an rdflib
SPARQL algebra tree / ``Query`` object — runnable directly via
``rdflib.plugins.sparql.evaluate.evalQuery`` or serializable back to query
text via ``rdflib.plugins.sparql.algebra.translateAlgebra``.

The hard part decoding has that encoding doesn't: rdflib's evaluator
requires *expression* nodes (``RelationalExpression``, ``Builtin_BOUND``,
``Function``, ...) to be actual ``Expr`` instances with a bound ``_evalfn``
(``rdflib.plugins.sparql.parserutils.value()`` raises on a plain
``CompValue`` used as an expression — "What do I do with this CompValue?").
That binding happens once, at *parse* time, via each grammar production's
``Comp(name, ...).setEvalFn(fn)`` call in ``rdflib.plugins.sparql.parser``.
Rather than hand-transcribing that table (name -> evalfn) — which would
silently drift out of sync with whatever rdflib version is actually
installed — ``_discover_expr_evalfns()`` below rebuilds it by walking the
live pyparsing grammar object graph in that module and collecting every
``Comp`` with a bound ``evalfn``. Same generic-mirror principle as the
encoder in ``to_rdf.py`` and the design note in ``vocab.py``.
"""

from __future__ import annotations

from typing import Any, Optional

from pyparsing import ParserElement
from rdflib import BNode, Graph, Literal, URIRef, Variable
from rdflib.collection import Collection
from rdflib.namespace import RDF
from rdflib.paths import AlternativePath, InvPath, MulPath, NegatedPath, SequencePath
from rdflib.plugins.sparql.parserutils import CompValue, Expr
from rdflib.plugins.sparql.sparql import Prologue, Query, Update

from .vocab import PY_STR_DATATYPE, QUERY, QUERY_COLLECTION, SALG, UPDATE, UPDATE_OPERATION, VARIABLE_DATATYPE

_SALG_NS = str(SALG)

# (node name, key) pairs whose value must decode to a genuine Python
# int/bool, not merely an rdflib Literal that happens to compare equal to
# one — Slice.start/.length are passed straight to itertools.islice, which
# requires a real int; a boolean Literal is always truthy in a plain Python
# `if` regardless of its actual value, since it's a non-empty string either
# way. See vocab.py's "Bare Python strings" section for the str case, which
# — unlike int/bool — is handled generically rather than by listing keys
# here.
#
# Scoped by node name, not key name alone: `start`/`length` are also
# `Builtin_SUBSTR`'s own parameter names (SPARQL's `SUBSTR(str, start[,
# length])`), a completely unrelated node where they must stay real
# `Literal`s — `operators.Builtin_SUBSTR` calls `numeric(expr.start)`,
# which raises `SPARQLTypeError` for anything that isn't a `Literal`
# instance. A bare key-name match previously converted `Builtin_SUBSTR`'s
# `start`/`length` to plain ints too, and `evalExtend` silently swallows
# that error into "leave the BIND target unbound" (same swallowing
# mechanism documented throughout this project's own findings) rather than
# raising - so a decoded `BIND(SUBSTR(...) AS ?z)` looked like it worked
# (no exception) while silently never binding `?z`. Confirmed via a real
# StarLayerGraph reproduction comparing results against plain rdflib.
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


def rdf_to_query(graph: Graph, root) -> Query:
    """Decode ``root`` (as produced by ``to_rdf.query_to_rdf``) back into an
    rdflib ``Query`` — same type ``prepareQuery``/``translateQuery`` return.

    The returned ``Query``'s ``Prologue`` is reconstructed from
    ``salg:base``/``salg:prologuePrefix`` on ``root`` (see vocab.py's
    "Prologue (BASE/PREFIX)" section) — this fixes real evaluation-time
    behavior (``BASE``-relative ``IRI()``/``URI()`` builtin resolution), but
    does *not* make ``algebra.translateAlgebra`` emit prefixed names: that
    function never reads ``query.prologue`` at all, confirmed empirically,
    so its output stays full-IRI-only regardless.
    """
    algebra = _decode(root, graph)

    # Recompute the _vars/lazy bookkeeping to_rdf.py deliberately doesn't
    # encode (see _INTERNAL_BOOKKEEPING_KEYS there) — the same two passes
    # translateQuery() itself runs on a freshly-built algebra tree, so the
    # decoded tree is evaluator-ready exactly like one built straight from
    # query text.
    from rdflib.plugins.sparql.algebra import _addVars, _traverseAgg, analyse
    from rdflib.plugins.sparql.algebra import simplify as _reorder_bgps
    from rdflib.plugins.sparql.algebra import traverse

    algebra = traverse(algebra, visitPost=_reorder_bgps)
    _traverseAgg(algebra, visitor=analyse)
    _traverseAgg(algebra, _addVars)

    return Query(_decode_prologue(root, graph), algebra)


def rdf_to_update(graph: Graph, root) -> Update:
    """Decode ``root`` (as produced by ``to_rdf.update_to_rdf``) back into an
    rdflib ``Update`` — same type ``prepareUpdate``/``translateUpdate``
    return, runnable via ``rdflib.plugins.sparql.update.evalUpdate``.

    Unlike a Query's algebra, an Update operation's WHERE clause (Modify)
    never gets the _vars/lazy bookkeeping pass in stock rdflib either —
    ``translateUpdate`` never calls ``_addVars``/``analyse`` the way
    ``translateQuery`` does for a SELECT/etc. — so there's nothing to
    recompute here to match. The request's single shared Prologue (see
    ``update_to_rdf``) is reconstructed the same way as a Query's, and
    assigned to every operation — ``evalUpdate`` reads ``u.prologue`` off
    each operation individually, even though it's the same object for all
    of them in a real ``prepareUpdate`` result too.
    """
    ops = _decode(graph.value(root, SALG.operations), graph)
    prologue = _decode_prologue(root, graph)
    for op in ops:
        op.prologue = prologue
    return Update(prologue, ops)


def rdf_to_collection(graph: Graph, root) -> list[Query]:
    """Decode ``root`` (as produced by ``to_rdf.queries_to_collection``)
    back into a list of independent, directly executable rdflib ``Query``
    objects, in the same order they were encoded.

    Each member is decoded via ``rdf_to_query`` individually — not the
    generic ``_decode`` walker an ordinary ``rdf:List`` goes through
    elsewhere in this module — since each member needs that function's own
    per-query handling (recomputed ``_vars``/``lazy`` bookkeeping via
    ``_addVars``/``analyse``, its own reconstructed Prologue), the same
    reason ``rdf_to_update`` doesn't reuse plain ``_decode`` for its own
    operations list's *individual members* either (only the list structure
    itself goes through the generic walker there).
    """
    query_nodes = Collection(graph, graph.value(root, SALG.queries))
    return [rdf_to_query(graph, node) for node in query_nodes]


def _decode_prologue(root, graph: Graph) -> Prologue:
    """Inverse of to_rdf._encode_prologue."""
    prologue = Prologue()
    base = graph.value(root, SALG.base)
    if base is not None:
        prologue.base = str(base)
    for binding in graph.objects(root, SALG.prologuePrefix):
        prefix = _decode(graph.value(binding, SALG.prefixLabel), graph)
        namespace = graph.value(binding, SALG.namespace)
        prologue.bind(prefix, namespace)
    return prologue


def _decode(node, graph: Graph):
    if node is None:
        return None
    if node == RDF.nil:
        return []

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
            local_name = str(comp_type)[len(_SALG_NS):]
            if local_name in _PATH_TYPE_NAMES:
                return _decode_path(node, local_name, graph)
            return _decode_comp_value(node, comp_type, graph)
        return node  # a plain blank node used directly as a query term

    raise NotImplementedError(
        f"starsparql: cannot decode node {node!r} of type {type(node).__name__}"
    )


_PATH_TYPE_NAMES = {"InvPath", "SequencePath", "AlternativePath", "MulPath", "NegatedPath"}


def _decode_path(node, local_name: str, graph: Graph):
    """Inverse of to_rdf._encode_path — see vocab.py's "Property paths"
    section for why these need dedicated handling (rdflib.paths.Path
    objects, not CompValue)."""
    if local_name == "InvPath":
        return InvPath(_decode(graph.value(node, SALG.arg), graph))
    if local_name == "SequencePath":
        return SequencePath(*_decode(graph.value(node, SALG.args), graph))
    if local_name == "AlternativePath":
        return AlternativePath(*_decode(graph.value(node, SALG.args), graph))
    if local_name == "MulPath":
        path = _decode(graph.value(node, SALG.path), graph)
        mod = str(graph.value(node, SALG.mod))
        return MulPath(path, mod)
    if local_name == "NegatedPath":
        # NegatedPath.__init__ takes one arg (a URIRef/InvPath/AlternativePath)
        # and expands it into self.args itself — it doesn't accept an
        # already-expanded list, so build the instance directly and set
        # .args, matching exactly what __init__ would have produced. Safe:
        # Path.eval/.n3/__repr__ only ever read .args, never re-derive it.
        obj = object.__new__(NegatedPath)
        obj.args = _decode(graph.value(node, SALG.args), graph)
        return obj
    raise NotImplementedError(f"starsparql: no decoder for path type {local_name!r}")


# Reserved key names _encode_prologue (to_rdf.py) writes directly onto a
# query/update root node — see _decode_comp_value's use of this below.
_PROLOGUE_KEYS = {"base", "prologuePrefix"}

_AUXILIARY_ROOT_MARKERS = {QUERY, UPDATE, UPDATE_OPERATION, QUERY_COLLECTION}


def _comp_value_type(node, graph: Graph) -> Optional[URIRef]:
    types = [t for t in graph.objects(node, RDF.type) if str(t).startswith(_SALG_NS)]
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
        result[graph_term] = _decode(graph.value(qnode, SALG.triples), graph)
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
    name = str(type_uri)[len(_SALG_NS):]
    kwargs: dict = {}
    for pred, obj in graph.predicate_objects(node):
        if pred == RDF.type or not str(pred).startswith(_SALG_NS):
            continue
        key = str(pred)[len(_SALG_NS):]
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
        value = _decode(obj, graph)
        if (name, key) in _PLAIN_VALUE_KEYS:
            value = _to_python_deep(value)
        kwargs[key] = value

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
        # every decode. See starsparql.triple_term for why.
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
            # fragment, not an expression. rdflib's own algebra.translateExists
            # sets `.graph` as a real instance attribute for exactly this
            # reason; a plain `result.update(kwargs)` here only stores it as
            # a dict key, so evaluating a decoded EXISTS/NOT EXISTS node
            # crashes ("What do I do with this CompValue?") the moment its
            # `.graph` is more than a single triple - confirmed via a real
            # StarLayerGraph reproduction. Mirror translateExists exactly.
            result.graph = kwargs["graph"]
        return result

    return CompValue(name, **kwargs)
