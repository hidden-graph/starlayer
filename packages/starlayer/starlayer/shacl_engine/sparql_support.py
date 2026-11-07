"""SHACL 1.2 SPARQL-Related Features, the parts every SPARQL-based construct shares.

* Prefix declarations (``sh:prefixes`` / ``sh:declare`` / ``owl:imports``, with the ontology fallback).
* Query checking: the queries the spec forbids (MINUS, VALUES over a pre-bound variable, SERVICE, ``AS ?prebound``) raise ``ShapeError``.
* Running a query on the data graph with pre-bound variables: through the graph's own ``sparql_query``
  (``interface.SparqlCapable``; every engine graph is Oxigraph-backed and has one).
* Mapping solutions to validation results, message templates, the ``$PATH`` substitution, and the two SPARQL node
  expressions (``sh:select``, ``sh:sparqlExpr``); ``expressions.py`` dispatches to them.
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Mapping
from functools import lru_cache
from typing import Any

from starlayer.shacl_engine.components.registry import Violation
from starlayer.shacl_engine.interface import Solutions
from starlayer.shacl_engine.plan import SH, Path, Plan, Shape, ShapeError, Term
from starlayer.shacl_engine.terms import OWL, RDF, Literal
from starlayer.shacl_engine.terms import NamedNode as URIRef
from starlayer.shacl_engine.terms import text as text_of

# --------------------------------------------------------------------------------------------------------------------
# Prefix declarations

_PREFIX_HOLDER_TYPES = (OWL.Ontology, SH.DataGraph, SH.ShapesGraph, SH.RulesGraph)


def _declarations(graph: Any, holders: Iterable[Term]) -> dict[str, str]:
    found: dict[str, str] = {}
    for holder in holders:
        for decl in graph.objects(holder, SH.declare):
            prefixes = [text_of(p) for p in graph.objects(decl, SH.prefix)]
            namespaces = [text_of(n) for n in graph.objects(decl, SH.namespace)]
            if len(prefixes) != 1 or len(namespaces) != 1:
                raise ShapeError(f"{decl!r}: a prefix declaration needs exactly one sh:prefix and one sh:namespace")
            if found.setdefault(prefixes[0], namespaces[0]) != namespaces[0]:
                raise ShapeError(f"prefix {prefixes[0]!r} is declared with two different namespaces")
    return found


def _import_closure(graph: Any, starts: Iterable[Term]) -> list[Term]:
    """``sh:prefixes/(^owl:versionIRI)?/(owl:imports/(^owl:versionIRI)?)*``: the declaring nodes, version IRIs resolved."""
    seen: dict = {}
    queue = list(starts)
    while queue:
        node = queue.pop()
        if node in seen:
            continue
        seen[node] = None
        queue.extend(graph.subjects(OWL.versionIRI, node))
        queue.extend(graph.objects(node, OWL.imports))
    return list(seen)


def prefixes_of(graph: Any, holder: Term) -> dict[str, str]:
    """The prefix map for a query whose ``sh:prefixes`` lives on ``holder``, read from ``graph`` (no plan, no cache)."""
    explicit = list(graph.objects(holder, SH.prefixes))
    if explicit:
        return _declarations(graph, _import_closure(graph, explicit))
    # no sh:prefixes: the declarations of the sh:ShapesGraph-like nodes win; an owl:Ontology declare only adds
    # prefixes they do not already bind (the W3C prefixes-002 case has a distractor with the same prefix).
    primary = [s for t in _PREFIX_HOLDER_TYPES[1:] for s in graph.subjects(RDF.type, t)]
    decls = _declarations(graph, primary)
    for p, ns in _declarations(graph, list(graph.subjects(RDF.type, OWL.Ontology))).items():
        decls.setdefault(p, ns)
    return decls


def prefixes_for(plan: Plan, holder: Term) -> dict[str, str]:
    """The prefix map for a query whose ``sh:prefixes`` lives on ``holder`` (cached per plan)."""
    key = ("prefixes", holder)
    if key not in plan.sparql_cache:
        plan.sparql_cache[key] = prefixes_of(plan.shapes_graph, holder)
    return plan.sparql_cache[key]


def with_prefixes(plan: Plan, holder: Term, text: str) -> str:
    header = "".join(f"PREFIX {p}: <{ns}>\n" for p, ns in prefixes_for(plan, holder).items())  # str-ok: prefix and namespace strings
    return header + text


# --------------------------------------------------------------------------------------------------------------------
# Query checking (the forbidden constructs of the spec's pre-binding appendix)


@lru_cache(maxsize=512)
def _analyse(text: str) -> tuple[str, tuple[str, ...], tuple]:
    """Parse ``text`` with StarLayer's own SPARQL parser and collect what the checks need.

    Returns ``(query form, projected variable names, constructs)``, ``constructs`` being, in document order,
    ``("minus",)``, ``("service",)``, ``("values", {names})`` and ``("assign", name)`` (a BIND, a SELECT expression or a
    GROUP BY alias target) found anywhere in the query, sub-selects and EXISTS patterns included."""
    from starlayer.sparql.parse_sparql import (
        Node,
        _pattern_vars,
        _values_vars,
        parse_sparql,
    )

    ast = parse_sparql(text)
    found: list[tuple] = []

    def walk(item: Any) -> None:
        if isinstance(item, Node):
            if item.kind == "Minus":
                found.append(("minus",))
            elif item.kind == "Service":
                found.append(("service",))
            elif item.kind == "Values":
                found.append(("values", frozenset(_var_name(v) for v in item.f["vars"])))
            elif item.kind in ("Bind", "ProjectExpr", "GroupAs"):
                found.append(("assign", _var_name(item.f["var"])))
            for value in item.f.values():
                walk(value)
        elif isinstance(item, (list, tuple)):
            for value in item:
                walk(value)

    walk(ast.f.get("where"))
    walk(ast.f.get("projection"))
    walk(ast.f.get("group_by"))
    walk(ast.f.get("values"))  # the trailing VALUES clause
    projection = ast.f.get("projection")
    if ast.kind != "SelectQuery":
        projected: tuple[str, ...] = ()
    elif projection is None:  # SELECT *: every variable in scope
        projected = tuple(sorted(_var_name(v) for v in _pattern_vars(ast.f.get("where")) | _values_vars(ast)))
    else:
        projected = tuple(_var_name(p.f["var"]) for p in projection)
    return ast.kind, projected, tuple(found)


def check_query(plan: Plan, text: str, prebound: Iterable[str], *, ask: bool = False) -> tuple[str, ...]:
    """Parse ``text`` with StarLayer's own SPARQL parser and reject what the spec forbids; return the projected variable names.

    Rejected: unparseable text; a SELECT where an ASK is required and vice versa; MINUS; SERVICE; a VALUES block that
    mentions a pre-bound variable (the draft's rule, SPARQL Appendix A; a VALUES over other variables is allowed, which
    is a DELIBERATE DEVIATION from the vendored W3C fixture ``unsupported-sparql-002`` and from pySHACL, both of which
    follow the older rule that forbids every VALUES); ``AS`` (BIND, or a SELECT expression) of a pre-bound variable.

    The checks read the parser's AST; no rdflib parse is involved (running the query is a separate step)."""
    prebound = frozenset(prebound)
    key = ("checked", text, prebound, ask)
    if key in plan.sparql_cache:
        return plan.sparql_cache[key]
    try:
        form, projected, constructs = _analyse(text)
    except Exception as exc:  # noqa: BLE001  (any parser failure means the shapes graph is ill-formed)
        raise ShapeError(f"SPARQL query does not parse: {exc}") from exc
    want = "AskQuery" if ask else "SelectQuery"
    if form != want:
        raise ShapeError(f"expected a {want}, got {form}")  # str-ok: want is the query form name
    for construct in constructs:
        if construct[0] == "minus":
            raise ShapeError("MINUS is not allowed in a SHACL SPARQL query")
        if construct[0] == "service":
            raise ShapeError("SERVICE is not allowed in a SHACL SPARQL query")
        if construct[0] == "values":
            # SHACL 1.2 SPARQL Appendix A: "SPARQL queries MUST not contain a VALUES clause that mentions any potentially
            # pre-bound variable". A VALUES that mentions only other variables is allowed.
            clash = sorted(construct[1] & prebound)
            if clash:
                raise ShapeError(f"VALUES must not mention the pre-bound variable ?{clash[0]} in a SHACL SPARQL query")  # str-ok: a variable name
        if construct[0] == "assign" and construct[1] in prebound:
            raise ShapeError(f"a SHACL SPARQL query must not assign the pre-bound variable ?{construct[1]}")  # str-ok: a variable name
    plan.sparql_cache[key] = projected
    return projected


# --------------------------------------------------------------------------------------------------------------------
# Running queries


def _var_name(variable: Any) -> str:
    """The name of a variable of the parser's AST (a ``pyoxigraph.Variable``)."""
    return variable.value


def run_query(
    graph: Any, text: str, init_bindings: Mapping[str, Term] | None = None, custom_functions: Mapping[Any, Any] | None = None
) -> Solutions:
    """Run ``text`` on ``graph`` through its ``sparql_query`` (every engine graph has one: Oxigraph runs the text).
    ``custom_functions`` maps function IRIs to Python callables."""
    return graph.sparql_query(text, init_bindings, custom_functions)


def shacl_functions(ctx: Any) -> dict[Any, Any]:
    """The shapes graph's ``sh:ListParameterExpressionFunction`` instances as callables by IRI, for the query being run
    (SPARQL Extensions 7.3: "SHOULD register a function"). The call's arguments become the scope ``0, 1, ...`` of the
    body expression, which must have exactly one output node, else the call is a SPARQL error (the function call gives no
    value). Read once per plan: the shapes graph does not change during a run."""
    shapes = ctx.shapes
    cache = ctx.plan.sparql_cache
    functions = cache.get(("shacl-functions",))
    if functions is not None:
        return functions
    from starlayer.shacl_engine.expressions import (
        EvaluationFailure,
        evaluate_expression,
    )

    def make(fn: Term, body: Term) -> Any:
        def call(*args: Term) -> Term | None:
            try:
                out = evaluate_expression(ctx, body, None, {i: [a] for i, a in enumerate(args)})
            except (EvaluationFailure, ShapeError):
                return None
            return out[0] if len(out) == 1 else None

        return call

    functions = cache[("shacl-functions",)] = {
        fn: make(fn, body)
        for fn in shapes.subjects(RDF.type, SH.ListParameterExpressionFunction)
        if isinstance(fn, URIRef) and (body := next(iter(shapes.objects(fn, SH.bodyExpression)), None)) is not None
    }
    return functions


def run_select(ctx: Any, text: str, bindings: Mapping[str, Term], *, require_this: bool = True) -> Solutions:
    projected = check_query(ctx.plan, text, bindings)
    if require_this and "this" not in projected:
        raise ShapeError("a SHACL SPARQL SELECT query must project ?this")
    return run_query(ctx.data, text, bindings, shacl_functions(ctx))


def run_ask(ctx: Any, text: str, bindings: Mapping[str, Term]) -> bool:
    check_query(ctx.plan, text, bindings, ask=True)
    return bool(run_query(ctx.data, text, bindings, shacl_functions(ctx)).boolean)


# --------------------------------------------------------------------------------------------------------------------
# $PATH, messages, solutions -> violations


def path_to_sparql(path: Path) -> str:
    if path.kind == "pred":
        return f"<{path.iri.value}>"
    args = [path_to_sparql(a) for a in path.args]
    if path.kind == "inverse":
        return f"^({args[0]})"  # str-ok: args are SPARQL path strings
    if path.kind == "seq":
        return "(" + "/".join(args) + ")"
    if path.kind == "alt":
        return "(" + "|".join(args) + ")"
    suffix = {"zero_or_more": "*", "one_or_more": "+", "zero_or_one": "?"}[path.kind]
    return f"({args[0]}){suffix}"  # str-ok: args are SPARQL path strings


_PATH_VAR = re.compile(r"[$?]PATH\b")


def substitute_path(text: str, shape: Shape) -> str:
    """For a property shape, replace ``$PATH`` by the SPARQL form of ``sh:path``; node shapes leave it unbound."""
    if shape.path is None:
        return text
    return _PATH_VAR.sub(lambda _m: path_to_sparql(shape.path), text)


_TEMPLATE = re.compile(r"\{[?$]([A-Za-z_][A-Za-z0-9_]*)\}")


def fill_template(message: Term, values: Mapping[str, Term]) -> Term:
    """Replace ``{?var}`` / ``{$var}`` in a message literal by the lexical form of the variable's value."""
    if not isinstance(message, Literal):
        return message

    def one(m: re.Match) -> str:
        v = values.get(m.group(1))
        return m.group(0) if v is None else text_of(v)

    filled = _TEMPLATE.sub(one, message.value)
    return Literal(filled, language=message.language) if message.language else Literal(filled, datatype=message.datatype)


def is_true(value: Term) -> bool:
    return text_of(value).lower() in ("true", "1")


def violations_from_solutions(
    solutions: Solutions,
    *,
    shape: Shape,
    focus: Term,
    bindings: Mapping[str, Term],
    messages: Iterable[Term],
    source_constraint: Term = None,
    severity: Term = None,
    graph: Any = None,
    annotation_source: Term = None,
) -> list[Violation]:
    """One violation per solution: ``?this`` -> focus (the pre-bound node), ``?path`` (an IRI) -> sh:resultPath else the
    property shape's path, ``?value`` -> sh:value else (node shapes) the focus node, ``?message`` -> message else the
    given templates, filled. A solution with ``?failure true`` makes the whole validation fail."""
    messages = tuple(messages)
    out: list[Violation] = []
    for row in solutions.rows:
        failure = row.get("failure")
        if failure is not None and isinstance(failure, Literal) and is_true(failure):
            raise ShapeError("a SPARQL constraint query reported ?failure true")
        path_term = row.get("path")
        path = Path(kind="pred", iri=path_term, node=path_term) if isinstance(path_term, URIRef) else None
        value = row.get("value", None if shape.is_property else focus)
        if "message" in row:
            msgs: tuple[Term, ...] = (row["message"],)
        else:
            known = {**bindings, **row}
            msgs = tuple(fill_template(m, known) for m in messages)
        annotations = (
            result_annotations(graph, annotation_source, row) if graph is not None and annotation_source is not None else ()
        )
        out.append(
            Violation(
                value=value,
                path=path,
                messages=msgs,
                source_constraint=source_constraint,
                severity=severity,
                annotations=annotations,
            )
        )
    return out


def result_annotations(graph: Any, source: Term, row: Mapping[str, Term]) -> tuple[tuple[Term, Term], ...]:
    """``sh:resultAnnotation`` of a ``sh:sparql`` constraint or a SELECT validator (SHACL 1.2 SPARQL-Related Features):
    each annotation has one ``sh:annotationProperty`` and either ``sh:annotationVarName`` (the variable's value in the
    solution row; no triple if it is unbound) or ``sh:annotationValue`` (every value). Entries without exactly one
    property are ignored, as the old validator does."""
    out: list[tuple[Term, Term]] = []
    for ann in graph.objects(source, SH.resultAnnotation):
        props = list(graph.objects(ann, SH.annotationProperty))
        if len(props) != 1:
            continue
        names = list(graph.objects(ann, SH.annotationVarName))
        if names:
            value = row.get(text_of(names[0]))
            if value is not None:
                out.append((props[0], value))
            continue
        for value in graph.objects(ann, SH.annotationValue):
            out.append((props[0], value))
    return tuple(out)


# --------------------------------------------------------------------------------------------------------------------
# SPARQL node expressions (sh:select, sh:sparqlExpr)


def _single_string(graph: Any, node: Term, pred: Term) -> str:
    values = list(graph.objects(node, pred))
    if len(values) != 1 or not isinstance(values[0], Literal):
        raise ShapeError(f"{node!r}: exactly one string literal {text_of(pred)} is required")
    return values[0].value


def _scope_variable(name: Any) -> str:
    """SPARQL variable for a scope entry: a string as is; an integer n is ``arg<n>``; a parameter path IRI its local name."""
    if isinstance(name, int):
        return f"arg{name}"
    if isinstance(name, URIRef):
        iri = name.value
        return iri[max(iri.rfind("#"), iri.rfind("/")) + 1 :]
    return str(name)


def eval_node_expression(ctx: Any, expr: Term, focus: Term | None, scope: Mapping[str, list] | None = None) -> list[Term]:
    """Output nodes of a ``sh:select`` or ``sh:sparqlExpr`` expression (called by ``expressions.py`` for those two
    operators; every other kind is evaluated there). ``this`` is pre-bound to ``focus`` when there is one, and every
    scope variable with exactly one value is pre-bound under its name (``sh:expression`` binds ``value``)."""
    plan = ctx.plan
    graph = plan.shapes_graph
    bindings = {_scope_variable(k): v[0] for k, v in (scope or {}).items() if len(v) == 1}
    if focus is not None:
        bindings["this"] = focus
    if (expr, SH.select, None) in graph:
        text = with_prefixes(plan, expr, _single_string(graph, expr, SH.select))
        projected = check_query(plan, text, bindings)
        if len(projected) != 1:
            raise ShapeError(f"{expr!r}: a select expression must project exactly one variable")
        var = projected[0]
    elif (expr, SH.sparqlExpr, None) in graph:
        body = _single_string(graph, expr, SH.sparqlExpr)
        text = with_prefixes(plan, expr, f"SELECT ({body} AS ?result) WHERE {{}}")
        check_query(plan, text, bindings)
        var = "result"
    else:
        raise ShapeError(f"{expr!r}: not a SPARQL node expression")
    rows = run_query(ctx.data, text, bindings, shacl_functions(ctx)).rows
    return [row[var] for row in rows if var in row]
