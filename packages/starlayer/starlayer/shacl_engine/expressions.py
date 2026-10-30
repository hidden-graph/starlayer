"""SHACL 1.2 Node Expressions (https://www.w3.org/TR/shacl12-node-expr/), the current ``shnex:`` and ``sparql:`` forms only.

Public API::

    evaluate_expression(ctx, expr, focus, bindings=None) -> list[Term]

``expr`` is a node of the shapes graph (``ctx.shapes``); ``focus`` the focus node (``None`` for none, as in a
``sh:targetNode`` expression); ``bindings`` maps variable names to a term or a list of terms (``shnex:var``). The result
is the ordered list of output nodes; an evaluation failure raises ``EvaluationFailure``, a malformed expression
``ShapeError``. Expressions read the shapes graph; paths, class membership and shape conformance run on the data graph
(the "focus graph").

Dispatch is a table: ``OPERATORS`` maps the *key* predicate of a blank-node expression to ``fn(ctx, expr, focus,
scope) -> list``. A non-blank node is a constant, a blank node without triples is empty, a blank node that is an RDF list
is a list expression. Auxiliary predicates (``shnex:nodes``, ``then``, ``else``, ``desc``, ``focusNode``) are read by the
operator that owns them. The ``sparql:`` functions are built into the same table by ``_register_sparql``.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from decimal import Decimal
from typing import Any

from rdflib import BNode, Literal, URIRef
from rdflib.namespace import RDF, XSD

from starlayer.graph.model import TripleTerm
from starlayer.shacl_engine.components.core_shape_based import shacl_list
from starlayer.shacl_engine.paths import eval_path, parse_path
from starlayer.shacl_engine.plan import SH, ShapeError, Term
from starlayer.shacl_engine.targets import _all_nodes, _class_closure

SHNEX = "http://www.w3.org/ns/shacl-node-expr#"
SPARQL_NS = "http://www.w3.org/ns/sparql#"

TRUE, FALSE = Literal(True), Literal(False)


class EvaluationFailure(Exception):
    """A node expression has no result for this data (Node Expressions 3.3), as opposed to an empty result."""


Scope = Mapping[str, list]
Operator = Callable[[Any, Term, "Term | None", Scope], list]
OPERATORS: dict[URIRef, Operator] = {}


def operator(*iris: str):
    def deco(fn: Operator) -> Operator:
        for iri in iris:
            OPERATORS[URIRef(iri)] = fn
        return fn

    return deco


def _n(name: str) -> URIRef:
    return URIRef(SHNEX + name)


# --------------------------------------------------------------------------------------------------------------------
# Entry points


def evaluate_expression(
    ctx: Any, expr: Term, focus: Term | None, bindings: Mapping[str, Any] | None = None
) -> list[Term]:
    scope = {
        k: (list(v) if isinstance(v, (list, tuple)) else [v])
        for k, v in (bindings or {}).items()
    }
    return _eval(ctx, expr, focus, scope)


def is_expression(graph: Any, node: Term) -> bool:
    """True if ``node`` is a blank node that is an operator expression (not a plain blank-node data value)."""
    return isinstance(node, BNode) and any(
        p in OPERATORS for p in _predicates(graph, node)
    )


def _predicates(graph: Any, node: Term) -> set:
    return {p for p, _o in graph.predicate_objects(node)}


def _eval(ctx: Any, expr: Term, focus: Term | None, scope: Scope) -> list[Term]:
    if not isinstance(expr, BNode):
        return [expr]  # constant: IRI, literal, triple term (rdf:nil included)
    g = ctx.shapes
    preds = _predicates(g, expr)
    if not preds:
        return []  # the empty expression
    if RDF.first in preds:
        return list(shacl_list(g, expr))  # list expression: its members
    keys = [p for p in preds if p in OPERATORS]
    if not keys:  # a call of a custom function declared in the shapes graph
        custom = _custom_functions(ctx)
        called = [p for p in preds if p in custom]
        if len(called) == 1 and len({custom[p] for p in called}) == 1:
            return _call_custom(ctx, expr, custom[called[0]], called[0], focus, scope)
        if len(called) > 1:
            raise ShapeError(f"{expr!r}: a node expression may call only one custom function, found {sorted(map(str, called))}")
    if len(keys) != 1:
        raise ShapeError(
            f"{expr!r}: a node expression needs exactly one operator predicate, found {sorted(map(str, keys))}"
        )
    return OPERATORS[keys[0]](ctx, expr, focus, scope)


# --------------------------------------------------------------------------------------------------------------------
# Custom functions (Node Expressions, "Custom Node Expressions"): sh:ListParameterExpressionFunction (called by its own IRI
# with a list of argument expressions, read in the body as [ shnex:arg 0 ]) and sh:NamedParameterExpressionFunction (called by
# the sh:path of one of its sh:keyParameter parameters, read in the body as [ shnex:arg <path> ]).


def _custom_functions(ctx: Any) -> dict[URIRef, Term]:
    """Call predicate -> function node, for the functions the shapes graph declares (built-in operators win)."""
    key = ("custom-functions",)
    cache = ctx.plan.sparql_cache
    if key not in cache:
        g = ctx.shapes
        reg: dict[URIRef, Term] = {}
        for fn in g.subjects(RDF.type, SH.ListParameterExpressionFunction):
            if isinstance(fn, URIRef) and fn not in OPERATORS:
                reg[fn] = fn
        for fn in g.subjects(RDF.type, SH.NamedParameterExpressionFunction):
            for param in g.objects(fn, SH.parameter):
                if (param, SH.keyParameter, TRUE) not in g:
                    continue
                for path in g.objects(param, SH.path):
                    if isinstance(path, URIRef) and path not in OPERATORS:
                        reg[path] = fn
        cache[key] = reg
    return cache[key]


def _call_custom(ctx: Any, expr: Term, fn: Term, pred: URIRef, focus: Term | None, scope: Scope) -> list:
    g = ctx.shapes
    body = next(iter(g.objects(fn, SH.bodyExpression)), None)
    if body is None:
        raise ShapeError(f"{fn!r}: a custom node expression function needs an sh:bodyExpression")
    arg_scope: dict = {}
    if (fn, RDF.type, SH.ListParameterExpressionFunction) in g:
        head = _one(ctx, expr, pred)
        any_empty = False
        for i, arg in enumerate(shacl_list(g, head)):
            nodes = _eval(ctx, arg, focus, scope)  # arguments are evaluated in the caller's scope
            if len(nodes) > 1:
                raise EvaluationFailure(f"argument {i} of a call of {fn} has more than one output node")
            if nodes:
                arg_scope[i] = nodes
            else:
                any_empty = True
        if any_empty:
            return []
        out = _eval(ctx, body, focus, arg_scope)
        if len(out) > 1:
            raise EvaluationFailure(f"the body of the list parameter function {fn} has more than one output node")
        return out
    for param in g.objects(fn, SH.parameter):  # every declared parameter, not only the key ones
        for path in g.objects(param, SH.path):
            exprs = list(g.objects(expr, path))
            if exprs:
                arg_scope[path] = _eval(ctx, exprs[0], focus, scope)
    return _eval(ctx, body, focus, arg_scope)


@operator(SHNEX + "arg")
def _arg(ctx, expr, focus, scope):
    key = _one(ctx, expr, _n("arg"))
    if isinstance(key, Literal):
        try:
            key = int(str(key))
        except ValueError:
            raise ShapeError(f"{expr!r}: shnex:arg must be an integer or a parameter path IRI") from None
    return list(scope.get(key, []))


def _values(ctx: Any, expr: Term, pred: URIRef) -> list:
    return list(ctx.shapes.objects(expr, pred))


def _one(ctx: Any, expr: Term, pred: URIRef, *, required: bool = True) -> Term | None:
    vs = _values(ctx, expr, pred)
    if len(vs) > 1 or (required and not vs):
        raise ShapeError(f"{expr!r}: exactly one {pred} is required")
    return vs[0] if vs else None


def _sub(
    ctx: Any,
    expr: Term,
    pred: URIRef,
    focus: Term | None,
    scope: Scope,
    *,
    default_focus: bool = False,
) -> list:
    """Output of the expression at ``expr pred ?x``; if absent: the focus node (``default_focus``) or ShapeError."""
    x = _one(ctx, expr, pred, required=not default_focus)
    if x is None:
        return [] if focus is None else [focus]
    return _eval(ctx, x, focus, scope)


def _args(ctx: Any, expr: Term, pred: URIRef) -> list[Term]:
    """The expressions of the list at ``expr pred (...)``."""
    head = _one(ctx, expr, pred)
    if (
        head != RDF.nil
        and next(iter(ctx.shapes.objects(head, RDF.first)), None) is None
    ):
        raise ShapeError(f"{expr!r}: the argument of {pred} must be an RDF list")
    return shacl_list(ctx.shapes, head)


def _integer(term: Term, what: str) -> int:
    if (
        isinstance(term, Literal)
        and term.datatype == XSD.integer
        and str(term).lstrip("+-").isdigit()
    ):
        n = int(str(term))
        if n >= 0:
            return n
    raise ShapeError(f"{what} must be a non-negative xsd:integer, got {term!r}")


def _bool(value: bool) -> list:
    return [TRUE if value else FALSE]


def _integer_literal(n: int) -> Literal:
    return Literal(n, datatype=XSD.integer)


# --------------------------------------------------------------------------------------------------------------------
# Core operators


@operator(SHNEX + "var")
def _var(ctx, expr, focus, scope):
    name = str(_one(ctx, expr, _n("var")))
    if name == "focusNode":
        return [] if focus is None else [focus]
    return list(scope.get(name, []))


@operator(SHNEX + "pathValues")
def _path_values(ctx, expr, focus, scope):
    node = _one(ctx, expr, _n("pathValues"))
    fexpr = _one(ctx, expr, _n("focusNode"), required=False)
    foci = [] if focus is None else [focus]
    if fexpr is not None:
        foci = _eval(ctx, fexpr, focus, scope)
    if len(foci) > 1:
        raise EvaluationFailure(
            "shnex:focusNode of a path values expression has more than one output node"
        )
    if not foci:
        return []
    key = ("path", node)
    path = ctx.plan.sparql_cache.get(key) or ctx.plan.sparql_cache.setdefault(
        key, parse_path(ctx.shapes, node)
    )
    return list(dict.fromkeys(eval_path(ctx.data, path, foci[0])))


@operator(SHNEX + "exists")
def _exists(ctx, expr, focus, scope):
    return _bool(bool(_eval(ctx, _one(ctx, expr, _n("exists")), focus, scope)))


@operator(SHNEX + "if")
def _if(ctx, expr, focus, scope):
    cond = _eval(ctx, _one(ctx, expr, _n("if")), focus, scope)
    branch = _one(ctx, expr, _n("then" if cond == [TRUE] else "else"), required=False)
    return (
        [] if branch is None else _eval(ctx, branch, focus, scope)
    )  # lazy: only the selected branch runs


@operator(SHNEX + "distinct")
def _distinct(ctx, expr, focus, scope):
    return list(
        dict.fromkeys(_eval(ctx, _one(ctx, expr, _n("distinct")), focus, scope))
    )


@operator(SHNEX + "intersection")
def _intersection(ctx, expr, focus, scope):
    outs = [_eval(ctx, m, focus, scope) for m in _args(ctx, expr, _n("intersection"))]
    if not outs:
        return []
    return [t for t in dict.fromkeys(outs[0]) if all(t in o for o in outs[1:])]


@operator(SHNEX + "concat")
def _concat(ctx, expr, focus, scope):
    return [
        t for m in _args(ctx, expr, _n("concat")) for t in _eval(ctx, m, focus, scope)
    ]


@operator(SHNEX + "remove")
def _remove(ctx, expr, focus, scope):
    drop = set(_eval(ctx, _one(ctx, expr, _n("remove")), focus, scope))
    return [t for t in _sub(ctx, expr, _n("nodes"), focus, scope) if t not in drop]


@operator(SHNEX + "limit")
def _limit(ctx, expr, focus, scope):
    return _sub(ctx, expr, _n("nodes"), focus, scope)[
        : _integer(_one(ctx, expr, _n("limit")), "shnex:limit")
    ]


@operator(SHNEX + "offset")
def _offset(ctx, expr, focus, scope):
    return _sub(ctx, expr, _n("nodes"), focus, scope)[
        _integer(_one(ctx, expr, _n("offset")), "shnex:offset") :
    ]


def _order_key(term: Term | None) -> tuple:
    """SPARQL ORDER BY order: unbound < blank node < IRI < literal; literals by value where comparable."""
    if term is None:
        return (0, "")
    if isinstance(term, BNode):
        return (1, str(term))
    if isinstance(term, URIRef):
        return (2, str(term))
    if isinstance(term, Literal):
        return (3, term)
    return (4, str(term))


@operator(SHNEX + "orderBy")
def _order_by(ctx, expr, focus, scope):
    nodes = _sub(ctx, expr, _n("nodes"), focus, scope)
    key_expr = _one(ctx, expr, _n("orderBy"))
    desc = _one(ctx, expr, _n("desc"), required=False)

    def key(n: Term) -> tuple:
        out = _eval(ctx, key_expr, n, scope)
        return _order_key(out[0] if out else None)

    return sorted(
        nodes, key=key, reverse=desc is not None and str(desc) in ("true", "1")
    )


@operator(SHNEX + "flatMap")
def _flat_map(ctx, expr, focus, scope):
    body = _one(ctx, expr, _n("flatMap"))
    return [
        t
        for n in _sub(ctx, expr, _n("nodes"), focus, scope, default_focus=True)
        for t in _eval(ctx, body, n, scope)
    ]


@operator(SHNEX + "filterShape")
def _filter_shape(ctx, expr, focus, scope):
    shape = _one(ctx, expr, _n("filterShape"))
    return [
        n for n in _sub(ctx, expr, _n("nodes"), focus, scope) if ctx.conforms(shape, n)
    ]


@operator(SHNEX + "findFirst")
def _find_first(ctx, expr, focus, scope):
    shape = _one(ctx, expr, _n("findFirst"))
    nodes = _sub(ctx, expr, _n("nodes"), focus, scope, default_focus=True)
    return next(([n] for n in nodes if ctx.conforms(shape, n)), [])


@operator(SHNEX + "matchAll")
def _match_all(ctx, expr, focus, scope):
    shape = _one(ctx, expr, _n("matchAll"))
    return _bool(
        all(
            ctx.conforms(shape, n)
            for n in _sub(ctx, expr, _n("nodes"), focus, scope, default_focus=True)
        )
    )


# --- aggregates ---------------------------------------------------------------------------------------------------


@operator(SHNEX + "count")
def _count(ctx, expr, focus, scope):
    return [
        _integer_literal(len(_eval(ctx, _one(ctx, expr, _n("count")), focus, scope)))
    ]


def _extremum(name: str, pick: Callable) -> Operator:
    def fn(ctx, expr, focus, scope):
        nodes = [
            n
            for n in _eval(ctx, _one(ctx, expr, _n(name)), focus, scope)
            if not isinstance(n, BNode)
        ]
        return [pick(nodes, key=_order_key)] if nodes else []

    return fn


OPERATORS[_n("min")] = _extremum("min", min)
OPERATORS[_n("max")] = _extremum("max", max)

_NUMERIC_RANK = {XSD.integer: 0, XSD.decimal: 1, XSD.float: 2, XSD.double: 3}


@operator(SHNEX + "sum")
def _sum(ctx, expr, focus, scope):
    """SPARQL SUM: numeric type promotion integer < decimal < float < double; a non-numeric input is a failure."""
    values: list = []
    rank = 0
    for n in _eval(ctx, _one(ctx, expr, _n("sum")), focus, scope):
        v = n.toPython() if isinstance(n, Literal) else None
        if isinstance(v, bool) or not isinstance(v, (int, float, Decimal)):
            raise EvaluationFailure(f"shnex:sum: {n!r} is not a number")
        rank = max(rank, _NUMERIC_RANK.get(n.datatype, 0 if isinstance(v, int) else 1))
        values.append(v)
    if rank == 0:
        return [Literal(sum(values), datatype=XSD.integer)]
    if rank == 1:
        return [
            Literal(
                sum((Decimal(str(v)) for v in values), Decimal(0)), datatype=XSD.decimal
            )
        ]
    return [
        Literal(
            float(sum(float(v) for v in values)),
            datatype=XSD.float if rank == 2 else XSD.double,
        )
    ]


# --- graph-wide ---------------------------------------------------------------------------------------------------


@operator(SHNEX + "instancesOf")
def _instances_of(ctx, expr, focus, scope):
    out: dict = {}
    for cls in _eval(ctx, _one(ctx, expr, _n("instancesOf")), focus, scope):
        if not isinstance(cls, URIRef):
            raise EvaluationFailure(f"shnex:instancesOf: {cls!r} is not an IRI")
        for c in _class_closure(ctx.data, cls):
            for inst in ctx.data.subjects(RDF.type, c):
                out.setdefault(inst, None)
    return list(out)


@operator(SHNEX + "nodesMatching")
def _nodes_matching(ctx, expr, focus, scope):
    shape = _one(ctx, expr, _n("nodesMatching"))
    return [n for n in _all_nodes(ctx.data) if ctx.conforms(shape, n)]


@operator(SHNEX + "conformsToShape")
def _conforms_to_shape(ctx, expr, focus, scope):
    members = _args(ctx, expr, _n("conformsToShape"))
    if len(members) != 2:
        raise ShapeError(
            f"{expr!r}: shnex:conformsToShape needs a list of two expressions"
        )
    outs = [_eval(ctx, m, focus, scope) for m in members]
    if any(len(o) > 1 for o in outs):
        raise EvaluationFailure(
            "an argument of shnex:conformsToShape has more than one output node"
        )
    if not all(outs):
        return []
    node, shape = outs[0][0], outs[1][0]
    if not isinstance(shape, URIRef):
        raise EvaluationFailure(
            f"shnex:conformsToShape: the shape {shape!r} is not an IRI"
        )
    return _bool(ctx.conforms(shape, node))


# --- SPARQL-Related Features: sh:select, sh:sparqlExpr (query machinery lives in sparql_support) -----------------------


@operator(str(SH.select), str(SH.sparqlExpr))
def _sparql_query_expression(ctx, expr, focus, scope):
    from starlayer.shacl_engine.sparql_support import eval_node_expression

    return eval_node_expression(ctx, expr, focus, scope)


# --------------------------------------------------------------------------------------------------------------------
# sparql: functions. Each call becomes ``SELECT (<template> AS ?result) WHERE {}`` on a scratch graph with the
# argument values pre-bound as ?a0, ?a1, ...; StarLayer's query layer supplies the SPARQL 1.2 built-ins.

_CALLS = (
    "abs bnode ceil concat contains datatype day encode_for_uri floor hours iri isBlank isIRI isLiteral isNumeric "
    "isTriple isURI lang langdir langMatches lcase md5 minutes month now object predicate rand regex replace round "
    "sameTerm seconds sha1 sha256 sha384 sha512 str strafter strbefore strdt strends strlang strlangdir strlen "
    "strstarts struuid subject substr timezone triple tz ucase uri uuid year hasLangdir"
).split()
_RENAMED = {"encode": "ENCODE_FOR_URI"}  # sparql:encode is SPARQL ENCODE_FOR_URI
_INFIX = {
    "equals": "=", "sameValue": "=", "not-equals": "!=", "less-than": "<", "greater-than": ">",
    "less-than-or-equal": "<=", "greater-than-or-equal": ">=", "plus": "+", "subtract": "-", "multiply": "*",
    "divide": "/",
}  # fmt: skip
_PREFIX = {"logical-not": "!", "unary-plus": "+", "unary-minus": "-"}

_scratch: Any = None


def _run_call(template: str, values: list) -> list:
    from starlayer.graph.graph.starlayer_graph import StarLayerGraph
    from starlayer.shacl_engine.sparql_support import starlayer_sparql_query

    global _scratch
    if _scratch is None:
        _scratch = StarLayerGraph()
    graph = (
        StarLayerGraph() if any(isinstance(v, TripleTerm) for v in values) else _scratch
    )
    for (
        v
    ) in values:  # the query layer resolves a triple term only if its graph has seen it
        if isinstance(v, TripleTerm):
            graph.add((BNode(), RDF.value, v))
    try:
        rows = starlayer_sparql_query(
            graph,
            f"SELECT ({template} AS ?result) WHERE {{}}",
            {f"a{i}": v for i, v in enumerate(values)},
        ).rows
    except Exception as exc:  # noqa: BLE001  (a SPARQL evaluation error is an evaluation failure)
        raise EvaluationFailure(f"SPARQL error in {template}: {exc}") from exc
    if not rows or "result" not in rows[0]:
        raise EvaluationFailure(f"SPARQL error in {template}")
    return [rows[0]["result"]]


_ERROR, _UNBOUND, _VALUE = "error", "unbound", "value"


def _arg_state(ctx, arg, focus, scope) -> tuple[str, Term | None]:
    try:
        out = _eval(ctx, arg, focus, scope)
    except EvaluationFailure:
        return (_ERROR, None)
    if len(out) > 1:
        return (_ERROR, None)
    return (_VALUE, out[0]) if out else (_UNBOUND, None)


def _sparql_args(ctx, expr, pred, focus, scope) -> list[tuple[str, Term | None]]:
    return [_arg_state(ctx, a, focus, scope) for a in _args(ctx, expr, pred)]


def _bound_values(states: list) -> list | None:
    """Values of the arguments; None if one is unbound; failure if one is in error (an error beats an unbound)."""
    if any(k == _ERROR for k, _ in states):
        raise EvaluationFailure(
            "an argument of a sparql: function has more than one output node or failed"
        )
    return None if any(k == _UNBOUND for k, _ in states) else [v for _, v in states]


def _ebv(term: Term | None) -> bool | None:
    from rdflib.plugins.sparql.operators import EBV
    from rdflib.plugins.sparql.sparql import SPARQLError

    try:
        return bool(EBV(term))
    except SPARQLError:
        return None


def _register_sparql() -> None:
    def simple(pred: URIRef, template: Callable[[int], str]) -> None:
        def fn(ctx, expr, focus, scope):
            values = _bound_values(_sparql_args(ctx, expr, pred, focus, scope))
            return [] if values is None else _run_call(template(len(values)), values)

        OPERATORS[pred] = fn

    def args_of(n: int) -> str:
        return ", ".join(f"?a{i}" for i in range(n))

    for name in _CALLS:
        simple(
            URIRef(SPARQL_NS + name),
            lambda n, name=name: (
                f"{name.upper() if name.islower() else name}({args_of(n)})"
            ),
        )
    # sparql:tz: the timezone of the *value*; rdflib's Turtle parser rewrites "...Z" as "...+00:00", and UTC is "Z"
    simple(
        URIRef(SPARQL_NS + "tz"),
        lambda _n_: 'IF(TZ(?a0) IN ("+00:00", "-00:00"), "Z", TZ(?a0))',
    )
    for name, sql in _RENAMED.items():
        simple(URIRef(SPARQL_NS + name), lambda n, sql=sql: f"{sql}({args_of(n)})")
    for name, op in _INFIX.items():
        simple(URIRef(SPARQL_NS + name), lambda _n_, op=op: f"(?a0 {op} ?a1)")
    for name, op in _PREFIX.items():
        simple(URIRef(SPARQL_NS + name), lambda _n_, op=op: f"({op}?a0)")


_register_sparql()


def _s(name: str) -> URIRef:
    return URIRef(SPARQL_NS + name)


@operator(SPARQL_NS + "bound")
def _sp_bound(ctx, expr, focus, scope):
    ((kind, _),) = _sparql_args(ctx, expr, _s("bound"), focus, scope)
    if kind == _ERROR:
        raise EvaluationFailure("the argument of sparql:bound failed")
    return _bool(kind == _VALUE)


@operator(SPARQL_NS + "coalesce")
def _sp_coalesce(ctx, expr, focus, scope):
    for kind, value in _sparql_args(ctx, expr, _s("coalesce"), focus, scope):
        if kind == _VALUE:
            return [value]
    raise EvaluationFailure("every argument of sparql:coalesce is unbound or failed")


@operator(SPARQL_NS + "if")
def _sp_if(ctx, expr, focus, scope):
    cond, then, other = _args(ctx, expr, _s("if"))
    kind, c = _arg_state(ctx, cond, focus, scope)
    truth = _ebv(c) if kind == _VALUE else None
    if truth is None:
        raise EvaluationFailure(
            "the condition of sparql:if is unbound, failed or not boolean"
        )
    kind, value = _arg_state(
        ctx, then if truth else other, focus, scope
    )  # lazy: only the selected branch
    if kind != _VALUE:
        raise EvaluationFailure("the selected branch of sparql:if is unbound or failed")
    return [value]


def _logical(name: str, absorbing: bool) -> None:
    def fn(ctx, expr, focus, scope):
        errored = False
        for kind, value in _sparql_args(ctx, expr, _s(name), focus, scope):
            truth = _ebv(value) if kind == _VALUE else None
            if truth is None:
                errored = True
            elif truth == absorbing:
                return _bool(absorbing)
        if errored:
            raise EvaluationFailure(f"an operand of sparql:{name} is unbound or failed")
        return _bool(not absorbing)

    OPERATORS[_s(name)] = fn


_logical("logical-or", True)
_logical("logical-and", False)


@operator(SPARQL_NS + "hasLang")
def _sp_has_lang(ctx, expr, focus, scope):
    """``sparql:hasLang ( literal tag )``: the fixtures give hasLang a language-tag argument (SPARQL's hasLANG has one
    argument); true if the literal's language tag equals ``tag``, case-insensitively."""
    values = _bound_values(_sparql_args(ctx, expr, _s("hasLang"), focus, scope))
    if values is None:
        return []
    if len(values) == 1:
        return _run_call("hasLANG(?a0)", values)
    lit, tag = values
    return _bool(
        bool(getattr(lit, "language", None))
        and str(lit.language).lower() == str(tag).lower()
    )
