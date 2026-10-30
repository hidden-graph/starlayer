"""SHACL 1.2 SPARQL-Related Features, the parts every SPARQL-based construct shares.

* Prefix declarations (``sh:prefixes`` / ``sh:declare`` / ``owl:imports``, with the ontology fallback).
* Query checking: the queries the spec forbids (MINUS, VALUES, SERVICE, ``AS ?prebound``) raise ``ShapeError``.
* Running a query on the data graph with pre-bound variables: through the graph's own ``sparql_query`` if it has one
  (``interface.SparqlCapable``), else through StarLayer's query layer (``starlayer_sparql_query``).
* Mapping solutions to validation results, message templates, the ``$PATH`` substitution, and the two SPARQL node
  expressions (``sh:select``, ``sh:sparqlExpr``); ``expressions.py`` dispatches to them.
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Iterator, Mapping
from contextlib import contextmanager
from functools import lru_cache
from typing import Any

from rdflib import OWL, RDF, Literal, URIRef
from rdflib.plugins.sparql.parserutils import CompValue

from starlayer.shacl_engine.components.registry import Violation
from starlayer.shacl_engine.interface import Solutions
from starlayer.shacl_engine.plan import SH, Path, Plan, Shape, ShapeError, Term

# --------------------------------------------------------------------------------------------------------------------
# Prefix declarations

_PREFIX_HOLDER_TYPES = (OWL.Ontology, SH.DataGraph, SH.ShapesGraph, SH.RulesGraph)


def _declarations(graph: Any, holders: Iterable[Term]) -> dict[str, str]:
    found: dict[str, str] = {}
    for holder in holders:
        for decl in graph.objects(holder, SH.declare):
            prefixes = [str(p) for p in graph.objects(decl, SH.prefix)]
            namespaces = [str(n) for n in graph.objects(decl, SH.namespace)]
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


def prefixes_for(plan: Plan, holder: Term) -> dict[str, str]:
    """The prefix map for a query whose ``sh:prefixes`` lives on ``holder`` (cached per plan)."""
    key = ("prefixes", holder)
    if key not in plan.sparql_cache:
        graph = plan.shapes_graph
        explicit = list(graph.objects(holder, SH.prefixes))
        if explicit:
            holders = _import_closure(graph, explicit)
            decls = _declarations(graph, holders)
        else:
            # no sh:prefixes: the declarations of the sh:ShapesGraph-like nodes win; an owl:Ontology declare only adds
            # prefixes they do not already bind (the W3C prefixes-002 case has a distractor with the same prefix).
            primary = [s for t in _PREFIX_HOLDER_TYPES[1:] for s in graph.subjects(RDF.type, t)]
            decls = _declarations(graph, primary)
            for p, ns in _declarations(graph, list(graph.subjects(RDF.type, OWL.Ontology))).items():
                decls.setdefault(p, ns)
        plan.sparql_cache[key] = decls
    return plan.sparql_cache[key]


def with_prefixes(plan: Plan, holder: Term, text: str) -> str:
    header = "".join(f"PREFIX {p}: <{ns}>\n" for p, ns in prefixes_for(plan, holder).items())
    return header + text


# --------------------------------------------------------------------------------------------------------------------
# Query checking (the forbidden constructs of the spec's pre-binding appendix)


@lru_cache(maxsize=512)
def _prepare(text: str) -> Any:
    from starlayer.graph.query.sparql_api import prepareQuery

    return prepareQuery(text)


def _walk(node: Any) -> Iterable[CompValue]:
    if isinstance(node, CompValue):
        yield node
        for v in node.values():
            yield from _walk(v)
    elif isinstance(node, (list, tuple, set)):
        for v in node:
            yield from _walk(v)


def check_query(plan: Plan, text: str, prebound: Iterable[str], *, ask: bool = False) -> tuple[str, ...]:
    """Parse ``text`` with StarLayer's parser and reject what the spec forbids; return the projected variable names.

    Rejected: unparseable text; a SELECT where an ASK is required and vice versa; MINUS; SERVICE; any VALUES block (the
    spec only forbids those that mention a pre-bound variable, the W3C fixture ``unsupported-sparql-002`` expects a
    failure for ``VALUES ?any {...}`` as well); ``AS`` (BIND, or a SELECT expression) of a pre-bound variable."""
    prebound = frozenset(prebound)
    key = ("checked", text, prebound, ask)
    if key in plan.sparql_cache:
        return plan.sparql_cache[key]
    try:
        query = _prepare(text)
    except Exception as exc:  # noqa: BLE001  (any parser failure means the shapes graph is ill-formed)
        raise ShapeError(f"SPARQL query does not parse: {exc}") from exc
    want = "AskQuery" if ask else "SelectQuery"
    if query.algebra.name != want:
        raise ShapeError(f"expected a {want}, got {query.algebra.name}")
    for part in _walk(query.algebra):
        if part.name == "Minus":
            raise ShapeError("MINUS is not allowed in a SHACL SPARQL query")
        if part.name == "ServiceGraphPattern":
            raise ShapeError("SERVICE is not allowed in a SHACL SPARQL query")
        if part.name == "values":
            raise ShapeError("VALUES is not allowed in a SHACL SPARQL query")
        if part.name == "Extend" and str(part.get("var")) in prebound:
            raise ShapeError(f"a SHACL SPARQL query must not assign the pre-bound variable ?{part.get('var')}")
    projected = tuple(str(v) for v in query.algebra.get("PV", ()) or ())
    plan.sparql_cache[key] = projected
    return projected


# --------------------------------------------------------------------------------------------------------------------
# Running queries


def starlayer_sparql_query(graph: Any, text: str, init_bindings: Mapping[str, Term] | None = None) -> Solutions:
    """Run ``text`` through StarLayer's query layer: its own SPARQL 1.2 parse (``prepareQuery``) and the graph's
    ``.query()``. Works for a ``StarLayerGraph`` / ``StarLayerDataset`` (and any rdflib-style graph)."""
    result = graph.query(_prepare(text), initBindings=dict(init_bindings or {}) or None)
    if result.type == "ASK":
        return Solutions(boolean=bool(result.askAnswer))
    rows = tuple({str(k): v for k, v in b.items() if v is not None} for b in result.bindings)
    return Solutions(variables=tuple(str(v) for v in result.vars), rows=rows)


def run_query(graph: Any, text: str, init_bindings: Mapping[str, Term] | None = None) -> Solutions:
    native = getattr(graph, "sparql_query", None)
    if native is not None:
        return native(text, init_bindings)
    return starlayer_sparql_query(graph, text, init_bindings)


@contextmanager
def _shacl_functions(ctx: Any) -> Iterator[None]:
    """Make the shapes graph's ``sh:ListParameterExpressionFunction`` instances callable by IRI from the query being run
    (SPARQL Extensions 7.3: "SHOULD register a function"). The call's arguments become the scope ``0, 1, ...`` of the
    body expression, which must have exactly one output node, else the call is a SPARQL error. Only for graphs queried
    through rdflib's evaluator (a native backend has no such registry)."""
    from rdflib.plugins.sparql.operators import (
        register_custom_function,
        unregister_custom_function,
    )
    from rdflib.plugins.sparql.sparql import SPARQLError

    from starlayer.shacl_engine.expressions import EvaluationFailure

    shapes = ctx.shapes
    active = ctx.plan.sparql_cache
    if getattr(ctx.data, "sparql_query", None) is not None or active.get(("shacl-functions-active",)):
        yield  # a native backend, or already registered by an enclosing query (a body that itself runs SPARQL)
        return
    registered: list[tuple[URIRef, Any]] = []

    def make(fn: Term, body: Term) -> Any:
        def call(*args: Term) -> Term:
            try:
                out = eval_node_expression(ctx, body, None, {i: [a] for i, a in enumerate(args)})
            except (EvaluationFailure, ShapeError) as exc:
                raise SPARQLError(str(exc)) from exc
            if len(out) != 1:
                raise SPARQLError(f"{fn}: the body must have exactly one output node, found {len(out)}")
            return out[0]

        return call

    active[("shacl-functions-active",)] = True
    try:
        for fn in shapes.subjects(RDF.type, SH.ListParameterExpressionFunction):
            body = next(iter(shapes.objects(fn, SH.bodyExpression)), None)
            if isinstance(fn, URIRef) and body is not None:
                func = make(fn, body)
                register_custom_function(fn, func, override=True)
                registered.append((fn, func))
        yield
    finally:
        active[("shacl-functions-active",)] = False
        for fn, func in registered:
            unregister_custom_function(fn, func)


def run_select(ctx: Any, text: str, bindings: Mapping[str, Term], *, require_this: bool = True) -> Solutions:
    projected = check_query(ctx.plan, text, bindings)
    if require_this and "this" not in projected:
        raise ShapeError("a SHACL SPARQL SELECT query must project ?this")
    with _shacl_functions(ctx):
        return run_query(ctx.data, text, bindings)


def run_ask(ctx: Any, text: str, bindings: Mapping[str, Term]) -> bool:
    check_query(ctx.plan, text, bindings, ask=True)
    with _shacl_functions(ctx):
        return bool(run_query(ctx.data, text, bindings).boolean)


# --------------------------------------------------------------------------------------------------------------------
# $PATH, messages, solutions -> violations


def path_to_sparql(path: Path) -> str:
    if path.kind == "pred":
        return f"<{path.iri}>"
    args = [path_to_sparql(a) for a in path.args]
    if path.kind == "inverse":
        return f"^({args[0]})"
    if path.kind == "seq":
        return "(" + "/".join(args) + ")"
    if path.kind == "alt":
        return "(" + "|".join(args) + ")"
    suffix = {"zero_or_more": "*", "one_or_more": "+", "zero_or_one": "?"}[path.kind]
    return f"({args[0]}){suffix}"


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
        return m.group(0) if v is None else str(v)

    text = _TEMPLATE.sub(one, str(message))
    return Literal(text, lang=message.language, datatype=None if message.language else message.datatype)


def is_true(value: Term) -> bool:
    return str(value).lower() in ("true", "1")


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
            value = row.get(str(names[0]))
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
        raise ShapeError(f"{node!r}: exactly one string literal {pred} is required")
    return str(values[0])


def _scope_variable(name: Any) -> str:
    """SPARQL variable for a scope entry: a string as is; an integer n is ``arg<n>``; a parameter path IRI its local name."""
    if isinstance(name, int):
        return f"arg{name}"
    if isinstance(name, URIRef):
        text = str(name)
        return text[max(text.rfind("#"), text.rfind("/")) + 1 :]
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
    with _shacl_functions(ctx):
        rows = run_query(ctx.data, text, bindings).rows
    return [row[var] for row in rows if var in row]
