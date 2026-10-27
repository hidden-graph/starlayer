"""Native support for SHACL 1.2 Node Expressions' ``sparql:`` namespace.

The W3C SHACL 1.2 Node Expressions Working Draft exposes SPARQL 1.1/1.2
built-in functions and operators as node expressions under
``sparql: = http://www.w3.org/ns/sparql#`` (e.g. ``sparql:strlen ( "hi" )``,
``sparql:greater-than ( 10 5 )``), entirely separate from the ``shnex:``
namespace ``starlayer.shacl/node_expressions.py`` implements. Per the W3C
SHACL 1.2 Node Expressions test suite's ``node-expr/shnex-sparql/``
fixtures, this covers 77 distinct functions/operators, one fixture file
each.

Rather than hand-reimplementing every SPARQL built-in (string functions,
numeric functions, hashing, date/time extraction, term-type predicates,
comparison/logical/arithmetic operators - rdflib already implements every
one of these correctly as part of its own SPARQL engine), each call is
translated into a tiny SPARQL ``SELECT (<expr> AS ?result) WHERE {}`` query,
evaluated with the already-computed argument values bound via
``initBindings``, and ``?result`` read back. This reuses rdflib's own
spec-compliant evaluator directly instead of a large, error-prone
reimplementation.

The query runs against a small, disposable ``StarLayerGraph`` built fresh
for each call (never against whatever ``data_graph`` object the caller
happens to have): in real ``validate()``/``apply_rules()`` usage,
``data_graph`` as handed to node-expression evaluation is
``pyshacl.graph_abstraction.RdfLibDataGraph`` wrapping a *plain*
``rdflib.Graph``, with no triple-term awareness at all. Using a proper
``StarLayerGraph`` instead isn't enough by itself, either:
`starlayer.graph`'s own ``_encode_init_bindings`` deliberately resolves a
triple-term value passed via ``initBindings`` to "not found" (a fresh,
unmatchable ``BNode``) unless that *exact* value is already registered in
*that specific graph instance's* own registry - by design, so a genuinely
foreign Python object can't silently compare equal to something in the
store it never belongs to. A triple-term value obtained from actual data
(e.g. via ``shnex:pathValues``) was never added to *any* graph this module
touches, so every RDF-1.2-specific function
(``isTRIPLE``/``TRIPLE``/``SUBJECT``/``PREDICATE``/``OBJECT``) silently
evaluated wrong even after routing the query through a real triple-term-
aware graph. Fixed by registering each triple-term-like argument value into
the scratch graph (a single throwaway triple, e.g. ``(BNode(), rdf:value,
value)``) *before* querying it - see ``_run_sparql_call()``'s docstring for
the full reasoning. This call's own SPARQL text never matches an actual
stored triple otherwise (its ``WHERE`` clause is always empty), so nothing
about the scratch graph's own emptiness matters beyond that registration.

``sparql:bound``/``sparql:coalesce``/``sparql:if`` need special handling
(their whole point is to *not* eagerly evaluate every argument, or to treat
an unbound argument as meaningful input rather than a hard error) - these
three are evaluated directly in Python rather than translated into a SPARQL
call. ``sparql:hasLang``/``hasLangdir``/``langdir``/``strlangdir`` (RDF 1.2
``rdf:dirLangString`` introspection/construction) are also evaluated
directly, since they operate on starlayer.graph's own internal ``DirLangString``
representation rather than anything rdflib's SPARQL engine natively knows
about.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from rdflib import BNode, Literal, URIRef
from rdflib.namespace import RDF, Namespace

from starlayer.shacl.types import is_triple_term_like

SPARQL = Namespace("http://www.w3.org/ns/sparql#")

# name -> SPARQL function-call name (as written in a SPARQL query, case
# exactly as SPARQL's own grammar expects - most are case-insensitive in
# practice, but written here matching the SPARQL 1.1 spec's own casing).
_FUNCTION_CALLS: dict[URIRef, str] = {
    SPARQL.strlen: "STRLEN",
    SPARQL.ucase: "UCASE",
    SPARQL.lcase: "LCASE",
    SPARQL.substr: "SUBSTR",
    SPARQL.contains: "CONTAINS",
    SPARQL.strstarts: "STRSTARTS",
    SPARQL.strends: "STRENDS",
    SPARQL.strbefore: "STRBEFORE",
    SPARQL.strafter: "STRAFTER",
    SPARQL["encode"]: "ENCODE_FOR_URI",  # SPARQL.encode would resolve to str.encode (Namespace subclasses str)
    SPARQL.concat: "CONCAT",
    SPARQL.langMatches: "LANGMATCHES",
    SPARQL.regex: "REGEX",
    SPARQL["replace"]: "REPLACE",  # SPARQL.replace would resolve to str.replace (Namespace subclasses str)
    SPARQL.abs: "ABS",
    SPARQL.ceil: "CEIL",
    SPARQL.floor: "FLOOR",
    SPARQL.round: "ROUND",
    SPARQL.year: "YEAR",
    SPARQL.month: "MONTH",
    SPARQL.day: "DAY",
    SPARQL.hours: "HOURS",
    SPARQL.minutes: "MINUTES",
    SPARQL.seconds: "SECONDS",
    SPARQL.timezone: "TIMEZONE",
    SPARQL.tz: "TZ",
    SPARQL.md5: "MD5",
    SPARQL.sha1: "SHA1",
    SPARQL.sha256: "SHA256",
    SPARQL.sha384: "SHA384",
    SPARQL.sha512: "SHA512",
    SPARQL.isIRI: "isIRI",
    SPARQL.isURI: "isURI",
    SPARQL.isBlank: "isBLANK",
    SPARQL.isLiteral: "isLITERAL",
    SPARQL.isNumeric: "isNUMERIC",
    SPARQL.bnode: "BNODE",
    SPARQL.iri: "IRI",
    SPARQL.uri: "URI",
    SPARQL.strdt: "STRDT",
    SPARQL.strlang: "STRLANG",
    SPARQL.uuid: "UUID",
    SPARQL.struuid: "STRUUID",
    SPARQL.str: "STR",
    SPARQL.lang: "LANG",
    SPARQL.datatype: "DATATYPE",
    SPARQL.sameTerm: "sameTerm",
    SPARQL.isTriple: "isTRIPLE",
    SPARQL.triple: "TRIPLE",
    SPARQL.subject: "SUBJECT",
    SPARQL.predicate: "PREDICATE",
    SPARQL.object: "OBJECT",
    SPARQL.now: "NOW",
    SPARQL.rand: "RAND",
}

# name -> infix SPARQL operator, rendered "(?a0 <op> ?a1)".
_INFIX_OPERATORS: dict[URIRef, str] = {
    SPARQL.equals: "=",
    SPARQL.sameValue: "=",  # value equality, same operator sameTerm() is distinct from
    SPARQL["not-equals"]: "!=",
    SPARQL["less-than"]: "<",
    SPARQL["greater-than"]: ">",
    SPARQL["less-than-or-equal"]: "<=",
    SPARQL["greater-than-or-equal"]: ">=",
    SPARQL.plus: "+",
    SPARQL.subtract: "-",
    SPARQL.multiply: "*",
    SPARQL.divide: "/",
    SPARQL["logical-and"]: "&&",
    SPARQL["logical-or"]: "||",
}

# name -> prefix SPARQL operator, rendered "(<op>?a0)".
_PREFIX_OPERATORS: dict[URIRef, str] = {
    SPARQL["logical-not"]: "!",
    SPARQL["unary-plus"]: "+",
    SPARQL["unary-minus"]: "-",
}

# Handled directly in Python, not translated to a SPARQL call - see module
# docstring for why each needs special treatment.
_SPECIAL_FORMS = (
    SPARQL.bound,
    SPARQL.coalesce,
    SPARQL["if"],
    SPARQL.hasLang,
    SPARQL.hasLangdir,
    SPARQL.langdir,
    SPARQL.strlangdir,
)

_ALL_PREDICATES = frozenset(
    set(_FUNCTION_CALLS) | set(_INFIX_OPERATORS) | set(_PREFIX_OPERATORS) | set(_SPECIAL_FORMS)
)

EvalArg = Callable[[Any], list]


class NodeExpressionError(ValueError):
    """A node expression is written wrongly (a definition error, as opposed to a value that has no result for some
    data). ``sh:values`` and ``sh:defaultValue`` treat an expression that errors on some data as having no value,
    but let this one through so a malformed shape is reported rather than quietly producing nothing."""


class EvaluationFailure(ValueError):
    """A node expression produces an *evaluation failure* (SHACL 1.2 Node Expressions 3.2, 3.3), as opposed to no
    output nodes. It is a plain ``ValueError``: callers such as ``sh:values`` treat it as "no value", while an
    enclosing ``sparql:`` function treats a failing argument as a SPARQL error (and ``sparql:coalesce``,
    ``sparql:logical-or`` and ``sparql:logical-and`` can recover from it)."""


_VALUE, _UNBOUND, _ERROR = "value", "unbound", "error"


def _arg_state(eval_arg: EvalArg, arg: Any) -> tuple[str, Any]:
    """Evaluate one argument of a ``sparql:`` function: ``(value, node)``, ``(unbound, None)`` for no output nodes, or
    ``(error, None)`` for a failing argument or one with more than one output node (Node Expressions 3.2.2 and 5)."""
    try:
        result = eval_arg(arg)
    except NodeExpressionError:
        raise
    except ValueError:
        return (_ERROR, None)
    if len(result) > 1:
        return (_ERROR, None)
    if not result:
        return (_UNBOUND, None)
    return (_VALUE, result[0])


def _collect_args(eval_arg: EvalArg, args: list) -> list | None:
    """Values of all arguments; ``None`` if one is unbound; raises :class:`EvaluationFailure` if one is an error.
    An error takes precedence over an unbound argument, whatever their order (Node Expressions 5)."""
    states = [_arg_state(eval_arg, a) for a in args]
    if any(kind == _ERROR for kind, _ in states):
        raise EvaluationFailure("an argument of a sparql: function expression failed or has more than one output node")
    if any(kind == _UNBOUND for kind, _ in states):
        return None
    return [value for _, value in states]


def _ebv(value: Any) -> bool | None:
    """SPARQL effective boolean value, ``None`` for a type error."""
    from rdflib.plugins.sparql.operators import EBV
    from rdflib.plugins.sparql.sparql import SPARQLError

    try:
        return bool(EBV(value))
    except SPARQLError:
        return None


def require_list_argument(sg: Any, expr: Any, label: str, arg: Any) -> None:
    """Raise :class:`NodeExpressionError` unless ``arg`` is an RDF list (``rdf:nil`` or a node with ``rdf:first``).

    The node-expression grammar gives a function or list operator its arguments as an RDF list. A bare node, e.g.
    ``sparql:year [ shnex:pathValues ex:d ]``, has no ``rdf:first``, so reading it as a list gave no arguments and
    the expression quietly produced no value (GitHub issue #8).
    """
    if arg != RDF.nil and next(iter(sg.graph.objects(arg, RDF.first)), None) is None:
        raise NodeExpressionError(
            f"Node expression {expr}: the argument of {label} must be an RDF list, "
            f"e.g. `{label} ( <expression> )`, not the bare node {arg}."
        )


def is_sparql_expr(sg: Any, expr: Any) -> bool:
    """True if ``expr`` is a blank node carrying exactly one ``sparql:`` defining predicate."""
    if not isinstance(expr, BNode):
        return False
    present = set(sg.graph.predicates(expr))
    return any(p in present for p in _ALL_PREDICATES)


def _defining_predicate(sg: Any, expr: Any) -> URIRef:
    present = set(sg.graph.predicates(expr))
    matches = [p for p in _ALL_PREDICATES if p in present]
    if len(matches) > 1:
        raise ValueError(
            f"Node expression {expr} has more than one sparql: defining predicate "
            f"({[str(m) for m in matches]}) - a blank node may only be one kind of "
            "sparql: expression."
        )
    return matches[0]


def _decode_triple_term(sg: Any, value: Any) -> Any:
    """Decode a flat-encoded ``urn:starlayer:tt:HASH`` URIRef back into
    a real triple-term value, if ``value`` is one - a no-op for everything
    else (an ordinary URIRef/Literal/BNode, or a value that's already a real
    triple term).

    Node expressions reading directly from ``data_graph`` (e.g.
    ``shnex:pathValues`` over a triple-term-valued property, via pySHACL's
    own ``value_nodes_from_path``) get back exactly this raw encoded form,
    not a decoded value - ``data_graph`` as handed to node-expression
    evaluation is pySHACL's plain, unwrapped ``RdfLibDataGraph``, which has
    no decoding step of its own (unlike report-graph decoding, which
    `starlayer.shacl.validator` does explicitly and separately). Fixing
    this at the `shnex:` layer generally is future work (see
    docs/shacl12-gap-matrix.md); this decodes specifically at the boundary
    into a `sparql:` function call, since an un-decoded value there is
    silently wrong for every RDF-1.2-specific function
    (`isTRIPLE`/`SUBJECT`/`PREDICATE`/`OBJECT`) and for value equality
    against a real triple-term constant.

    ``sg.graph``'s own ``_tt_adapter`` (the same ``TripleTermAdapter``
    instance ``starlayer.shacl.validator`` uses to encode *both* the data
    and shapes graphs for one `validate()`/`apply_rules()` call) already
    has the registry entry needed, since it's the same adapter that minted
    the hash in the first place. Falls back to a no-op if `sg.graph` has no
    such attribute (e.g. the `tests/w3c_shacl12/` harness, which never
    encodes anything at all - values are already real triple terms there).

    Returns a plain ``(subject, predicate, object)`` 3-tuple, not
    ``starlayer.shacl.adapters.TripleTermValue`` (``adapter.decode_term()``'s
    own return type) - a different class from `starlayer.graph`'s own
    ``starlayer.graph.model.triple.TripleTerm``, which is all
    ``StarLayerGraph.add()``/query-time coercion actually recognizes (a
    ``TripleTermValue`` passed directly crashes with "Object ... must be an
    rdflib term"). Mirrors the identical conversion
    ``starlayer.shacl.adapters._normalize_init_bindings`` already does for
    the same reason.
    """
    adapter = getattr(sg.graph, "_tt_adapter", None)
    if adapter is None:
        return value
    decoded = adapter.decode_term(value)
    if is_triple_term_like(decoded):
        return (decoded.subject, decoded.predicate, decoded.object)
    return decoded


def _run_sparql_call(template: str, arg_values: list) -> list:
    """Evaluate a SPARQL expression template against arg_values bound as ?a0, ?a1, ...

    Runs against a small ``StarLayerGraph`` built fresh for this one call,
    not any graph the caller already has: in real
    ``validate()``/``apply_rules()`` usage, the ``data_graph`` pySHACL's own
    node-expression dispatch hands this module is
    ``pyshacl.graph_abstraction.RdfLibDataGraph`` wrapping a *plain*
    ``rdflib.Graph``, with no triple-term awareness at all - and even a
    proper ``StarLayerGraph``/``_SparqlAwareEncodedGraph`` (e.g. the shapes
    graph, always available via ``sg.graph``) isn't sufficient by itself:
    `starlayer.graph`'s own ``_encode_init_bindings`` deliberately resolves
    a triple-term value passed via ``initBindings`` to "not found" (a fresh,
    unmatchable ``BNode``) unless that *exact* value is already registered
    in *that specific graph instance's own* registry - correct and
    deliberate ("giving correct 'zero rows' semantics rather than silently
    comparing a raw Python object against store terms it can never equal",
    per that function's own docstring), but it means a triple-term value
    obtained from actual data (e.g. via ``shnex:pathValues``) needs to be
    registered *somewhere* before any of `isTRIPLE`/`TRIPLE`/`SUBJECT`/
    `PREDICATE`/`OBJECT` can recognize it - querying the *shapes* graph
    doesn't help, since a data-graph-only triple term was never part of
    the shapes graph's own content either.

    Solved by registering each triple-term-like argument into this
    single-use scratch graph via one throwaway triple
    (``(BNode(), rdf:value, value)``) before querying - `StarLayerGraph.add()`
    populates its own internal registry as a side effect, and does so
    recursively for a nested triple term (one whose own subject/object is
    itself a triple term), so this one registration step is sufficient
    regardless of nesting depth. This call's own SPARQL text never matches
    an actual stored triple either way (its ``WHERE`` clause is always
    empty), so the scratch graph being otherwise empty doesn't matter.

    Returns [] if any bound argument is unresolvable by rdflib's evaluator
    (an unbound/error result), matching ordinary SPARQL error propagation -
    the caller (eval_expr's sparql:-dispatch) is responsible for the
    functions where an unbound *input* argument is meaningful rather than an
    error (sparql:bound/coalesce/if), which never call this helper with a
    genuinely unbound argument in the first place.
    """
    from rdflib.namespace import RDF

    from starlayer.graph.graph.starlayer_graph import StarLayerGraph

    scratch = StarLayerGraph()
    for value in arg_values:
        # A real TripleTerm-like object *or* a plain 3-tuple - StarLayerGraph
        # treats a bare 3-tuple as triple-term shorthand everywhere else
        # (e.g. `.add()`), and `_decode_triple_term()` deliberately returns
        # one instead of `starlayer.shacl.adapters.TripleTermValue`, so
        # this check must accept both forms or the registration below is
        # silently skipped for every value reaching this from that decode
        # step - confirmed live (the tuple form is the common case here).
        if is_triple_term_like(value) or (isinstance(value, tuple) and len(value) == 3):
            scratch.add((BNode(), RDF.value, value))

    init_bindings = {f"a{i}": v for i, v in enumerate(arg_values)}
    query = f"SELECT ({template} AS ?result) WHERE {{}}"
    try:
        rows = list(scratch.query(query, initBindings=init_bindings))
    except Exception as exc:
        raise EvaluationFailure(f"SPARQL error evaluating {template}: {exc}") from exc
    if not rows or rows[0][0] is None:
        raise EvaluationFailure(f"SPARQL error evaluating {template}")
    return [rows[0][0]]


def eval_sparql_expr(expr: Any, sg: Any, eval_arg: EvalArg) -> list:
    """Evaluate a ``sparql:``-tagged node expression. See module docstring."""
    pred = _defining_predicate(sg, expr)
    arg_list = next(iter(sg.graph.objects(expr, pred)))
    require_list_argument(sg, expr, "sparql:" + pred.rsplit("#", 1)[-1], arg_list)
    arg_exprs = list(sg.graph.items(arg_list))

    if pred == SPARQL.bound:
        (arg,) = arg_exprs
        kind, _ = _arg_state(eval_arg, arg)
        if kind == _ERROR:
            raise EvaluationFailure("the argument of sparql:bound failed or has more than one output node")
        return [Literal(kind == _VALUE)]

    if pred == SPARQL.coalesce:
        # skips arguments that are unbound or in error (Node Expressions 5); all of them unbound is an error
        for arg in arg_exprs:
            kind, value = _arg_state(eval_arg, arg)
            if kind == _VALUE:
                return [value]
        raise EvaluationFailure("every argument of sparql:coalesce is unbound or failed")

    if pred == SPARQL["if"]:
        cond_expr, then_expr, else_expr = arg_exprs
        kind, cond = _arg_state(eval_arg, cond_expr)
        is_true = _ebv(cond) if kind == _VALUE else None
        if is_true is None:
            raise EvaluationFailure("the condition of sparql:if is unbound, failed or has no boolean value")
        # only the selected branch counts; an unbound selected branch is an error as in SPARQL
        kind, value = _arg_state(eval_arg, then_expr if is_true else else_expr)
        if kind != _VALUE:
            raise EvaluationFailure("the selected branch of sparql:if is unbound or failed")
        return [value]

    if pred in (SPARQL["logical-or"], SPARQL["logical-and"]):
        # SPARQL 17.3.1 truth tables: an unbound or error operand is an error, which true (||) or false (&&) absorbs
        absorbing = pred == SPARQL["logical-or"]
        errored = False
        for arg in arg_exprs:
            kind, value = _arg_state(eval_arg, arg)
            truth = _ebv(value) if kind == _VALUE else None
            if truth is None:
                errored = True
            elif truth == absorbing:
                return [Literal(absorbing)]
        if errored:
            raise EvaluationFailure(f"an operand of {pred.rsplit('#', 1)[-1]} is unbound or failed")
        return [Literal(not absorbing)]

    if pred in (SPARQL.hasLang, SPARQL.hasLangdir, SPARQL.langdir, SPARQL.strlangdir):
        return _eval_dirlang_form(pred, arg_exprs, eval_arg)

    collected = _collect_args(eval_arg, arg_exprs)
    if collected is None:
        return []  # an unbound argument makes an ordinary function call unbound too
    arg_values = [_decode_triple_term(sg, v) for v in collected]

    if pred in _FUNCTION_CALLS:
        fn_name = _FUNCTION_CALLS[pred]
        placeholders = ", ".join(f"?a{i}" for i in range(len(arg_values)))
        return _run_sparql_call(f"{fn_name}({placeholders})", arg_values)

    if pred in _INFIX_OPERATORS:
        (a, b) = arg_values
        op = _INFIX_OPERATORS[pred]
        return _run_sparql_call(f"(?a0 {op} ?a1)", [a, b])

    if pred in _PREFIX_OPERATORS:
        (a,) = arg_values
        op = _PREFIX_OPERATORS[pred]
        return _run_sparql_call(f"({op}?a0)", [a])

    raise NotImplementedError(f"sparql: expression {pred} is not yet implemented.")


def _eval_dirlang_form(pred: URIRef, arg_exprs: list, eval_arg: EvalArg) -> list:
    from starlayer.graph.model.dirlangstring import DirLangString
    from starlayer.shacl.adapters import _try_decode_dirlangstring

    def _decode(value: Any) -> DirLangString | None:
        # A DirLangString reaching this module from real validate()/
        # apply_rules() usage has already been flat-encoded to a plain
        # Literal (starlayer.graph's internal dirlang-encoded datatype URI) by
        # the time pySHACL's node-expression dispatch hands it here - the same
        # flattening _decode_triple_term() above works around for triple
        # terms. An un-decoded flat-encoded Literal silently makes
        # hasLangdir/langdir/strlangdir wrong (hasLangdir false, langdir
        # "") for every real DirLangString value; this only passes when
        # called directly with a raw DirLangString instance (e.g. the W3C
        # suite's eval_expr()-direct harness, which never encodes anything).
        if isinstance(value, DirLangString):
            return value
        return _try_decode_dirlangstring(value)

    if pred == SPARQL.hasLang:
        collected = _collect_args(eval_arg, arg_exprs)
        if collected is None:
            return []
        lit, tag = collected[0], str(collected[1])
        language = lit.language if isinstance(lit, Literal) else None
        dirlang = _decode(lit)
        if dirlang is not None:
            language = dirlang.language
        return [Literal(bool(language) and str(language).lower() == tag.lower())]

    if pred == SPARQL.strlangdir:
        collected = _collect_args(eval_arg, arg_exprs)
        if collected is None:
            return []
        return [DirLangString(str(collected[0]), str(collected[1]), str(collected[2]))]

    collected = _collect_args(eval_arg, arg_exprs)
    if collected is None:
        return []
    dirlang = _decode(collected[0])

    if pred == SPARQL.hasLangdir:
        return [Literal(dirlang is not None)]

    if pred == SPARQL.langdir:
        if dirlang is None:
            return [Literal("")]
        return [Literal(dirlang.direction)]

    raise NotImplementedError(f"sparql: expression {pred} is not yet implemented.")
