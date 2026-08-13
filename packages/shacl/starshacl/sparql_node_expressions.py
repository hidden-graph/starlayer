"""Native support for SHACL 1.2 Node Expressions' ``sparql:`` namespace.

The W3C SHACL 1.2 Node Expressions Working Draft exposes SPARQL 1.1/1.2
built-in functions and operators as node expressions under
``sparql: = http://www.w3.org/ns/sparql#`` (e.g. ``sparql:strlen ( "hi" )``,
``sparql:greater-than ( 10 5 )``), entirely separate from the ``shnex:``
namespace ``starshacl/node_expressions.py`` implements. Confirmed via
the W3C SHACL 1.2 Node Expressions test suite's ``node-expr/shnex-sparql/``
fixtures - ~74 distinct functions/operators, one fixture file each.

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
happens to have) - confirmed live that in real
``validate()``/``apply_rules()`` usage, ``data_graph`` as handed to
node-expression evaluation is ``pyshacl.graph_abstraction.RdfLibDataGraph``
wrapping a *plain* ``rdflib.Graph``, with no triple-term awareness at all.
Using a proper ``StarLayerGraph`` instead isn't enough by itself, either:
`starlayergraph`'s own ``_encode_init_bindings`` deliberately resolves a
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
directly, since they operate on starlayergraph's own internal ``DirLangString``
representation rather than anything rdflib's SPARQL engine natively knows
about.
"""

from __future__ import annotations

from typing import Any, Callable

from rdflib import BNode, Literal, URIRef
from rdflib.namespace import Namespace

from starshacl.types import is_triple_term_like

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
    """Decode a flat-encoded ``urn:starshacl:tt:HASH`` URIRef back into
    a real triple-term value, if ``value`` is one - a no-op for everything
    else (an ordinary URIRef/Literal/BNode, or a value that's already a real
    triple term).

    Confirmed live that node expressions reading directly from
    ``data_graph`` (e.g. ``shnex:pathValues`` over a triple-term-valued
    property, via pySHACL's own ``value_nodes_from_path``) get back exactly
    this raw encoded form, not a decoded value - ``data_graph`` as handed to
    node-expression evaluation is pySHACL's plain, unwrapped
    ``RdfLibDataGraph``, which has no decoding step of its own (unlike
    report-graph decoding, which `starshacl.validator` does
    explicitly and separately). Fixing this at the `shnex:` layer generally
    is future work (see docs/shacl12-gap-matrix.md); this decodes
    specifically at the boundary into a `sparql:` function call, since an
    un-decoded value there is silently wrong for every RDF-1.2-specific
    function (`isTRIPLE`/`SUBJECT`/`PREDICATE`/`OBJECT`) and for value
    equality against a real triple-term constant.

    ``sg.graph``'s own ``_tt_adapter`` (the same ``TripleTermAdapter``
    instance ``starshacl.validator`` used to encode *both* the data
    and shapes graphs for one `validate()`/`apply_rules()` call - confirmed
    via `validator.py`'s `self.adapter.encode_graph(...)` calls sharing one
    adapter) already has the registry entry needed, since it's the same
    adapter that minted the hash in the first place. Falls back to a no-op
    if `sg.graph` has no such attribute (e.g. this session's
    `tests/w3c_suite/` harness, which never encodes anything at all - values
    are already real triple terms there).

    Returns a plain ``(subject, predicate, object)`` 3-tuple, not
    ``starshacl.adapters.TripleTermValue`` (``adapter.decode_term()``'s
    own return type) - a different class from `starlayergraph`'s own
    ``starlayergraph.model.triple.TripleTerm``, which is all
    ``StarLayerGraph.add()``/query-time coercion actually recognizes
    (confirmed live: handing it a ``TripleTermValue`` directly crashes with
    "Object ... must be an rdflib term"). Mirrors the identical conversion
    ``starshacl.adapters._normalize_init_bindings`` already does for
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
    not any graph the caller already has - confirmed live that in real
    ``validate()``/``apply_rules()`` usage, the ``data_graph`` pySHACL's own
    node-expression dispatch hands this module is
    ``pyshacl.graph_abstraction.RdfLibDataGraph`` wrapping a *plain*
    ``rdflib.Graph``, with no triple-term awareness at all - and even a
    proper ``StarLayerGraph``/``_SparqlAwareEncodedGraph`` (e.g. the shapes
    graph, always available via ``sg.graph``) isn't sufficient by itself:
    `starlayergraph`'s own ``_encode_init_bindings`` deliberately resolves
    a triple-term value passed via ``initBindings`` to "not found" (a fresh,
    unmatchable ``BNode``) unless that *exact* value is already registered
    in *that specific graph instance's own* registry - correct and
    deliberate ("giving correct 'zero rows' semantics rather than silently
    comparing a raw Python object against store terms it can never equal",
    per that function's own docstring), but it means a triple-term value
    obtained from actual data (e.g. via ``shnex:pathValues``) needs to be
    registered *somewhere* before any of `isTRIPLE`/`TRIPLE`/`SUBJECT`/
    `PREDICATE`/`OBJECT` can recognize it - confirmed empirically that
    querying the *shapes* graph doesn't help, since a data-graph-only
    triple term was never part of the shapes graph's own content either.

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
    from starlayergraph.graph.starlayer_graph import StarLayerGraph

    scratch = StarLayerGraph()
    for value in arg_values:
        # A real TripleTerm-like object *or* a plain 3-tuple - StarLayerGraph
        # treats a bare 3-tuple as triple-term shorthand everywhere else
        # (e.g. `.add()`), and `_decode_triple_term()` deliberately returns
        # one instead of `starshacl.adapters.TripleTermValue`, so
        # this check must accept both forms or the registration below is
        # silently skipped for every value reaching this from that decode
        # step - confirmed live (the tuple form is the common case here).
        if is_triple_term_like(value) or (isinstance(value, tuple) and len(value) == 3):
            scratch.add((BNode(), RDF.value, value))

    init_bindings = {f"a{i}": v for i, v in enumerate(arg_values)}
    query = f"SELECT ({template} AS ?result) WHERE {{}}"
    try:
        rows = list(scratch.query(query, initBindings=init_bindings))
    except Exception:
        return []
    if not rows or rows[0][0] is None:
        return []
    return [rows[0][0]]


def eval_sparql_expr(expr: Any, sg: Any, eval_arg: EvalArg) -> list:
    """Evaluate a ``sparql:``-tagged node expression. See module docstring."""
    pred = _defining_predicate(sg, expr)
    arg_list = next(iter(sg.graph.objects(expr, pred)))
    arg_exprs = list(sg.graph.items(arg_list))

    if pred == SPARQL.bound:
        (arg,) = arg_exprs
        return [Literal(len(eval_arg(arg)) > 0)]

    if pred == SPARQL.coalesce:
        for arg in arg_exprs:
            result = eval_arg(arg)
            if result:
                return [result[0]]
        return []

    if pred == SPARQL["if"]:
        cond_expr, then_expr, else_expr = arg_exprs
        cond_result = eval_arg(cond_expr)
        is_true = bool(cond_result) and bool(cond_result[0].toPython())
        return eval_arg(then_expr if is_true else else_expr)

    if pred in (SPARQL.hasLang, SPARQL.hasLangdir, SPARQL.langdir, SPARQL.strlangdir):
        return _eval_dirlang_form(pred, arg_exprs, eval_arg)

    arg_values = []
    for arg in arg_exprs:
        result = eval_arg(arg)
        if not result:
            return []  # an unbound argument makes an ordinary function call unbound too
        arg_values.append(_decode_triple_term(sg, result[0]))

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
    from starlayergraph.model.dirlangstring import DirLangString

    def _decode(value: Any) -> DirLangString | None:
        return value if isinstance(value, DirLangString) else None

    if pred == SPARQL.hasLang:
        lit_expr, tag_expr = arg_exprs
        lit_result, tag_result = eval_arg(lit_expr), eval_arg(tag_expr)
        if not lit_result or not tag_result:
            return []
        lit, tag = lit_result[0], str(tag_result[0])
        language = lit.language if isinstance(lit, Literal) else None
        dirlang = _decode(lit)
        if dirlang is not None:
            language = dirlang.language
        return [Literal(bool(language) and str(language).lower() == tag.lower())]

    if pred == SPARQL.strlangdir:
        value_expr, lang_expr, dir_expr = arg_exprs
        value_result, lang_result, dir_result = eval_arg(value_expr), eval_arg(lang_expr), eval_arg(dir_expr)
        if not (value_result and lang_result and dir_result):
            return []
        return [DirLangString(str(value_result[0]), str(lang_result[0]), str(dir_result[0]))]

    (lit_expr,) = arg_exprs
    lit_result = eval_arg(lit_expr)
    if not lit_result:
        return []
    dirlang = _decode(lit_result[0])

    if pred == SPARQL.hasLangdir:
        return [Literal(dirlang is not None)]

    if pred == SPARQL.langdir:
        if dirlang is None:
            return [Literal("")]
        return [Literal(dirlang.direction)]

    raise NotImplementedError(f"sparql: expression {pred} is not yet implemented.")
