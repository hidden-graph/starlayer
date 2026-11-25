"""The meta-SHACL preflight: a shapes graph checked against SHACL-for-SHACL before it is used (``meta_shacl=True``).

The meta-shapes graph is not assembled at run time. It is stored as ``starontology``'s ``shacl12-shacl.ttl`` (registry entry
``shacl_shacl``) and read by ``load_meta_shapes_graph``; ``starlayer.shacl.engine.meta`` runs the check. The build that produces
the stored graph lives in ``scripts/build_meta_shapes.py`` and is run by ``scripts/build_starontology.py``. It starts from the W3C
Data Shapes Working Group's own SHACL-for-SHACL (a pinned copy, ``packages/starlayer/starlayer/starontology/_sources/vendor/w3c-shacl-shacl.ttl``) and only adds to
it: ``shacl12-validation-shapes.ttl`` plus ``sh:deactivated`` on the few Working Group rules that are still stricter than
SHACL 1.2. A test fails if the stored file drifts from a fresh build, and ``test_wg_overrides.py`` fails when the Working Group
fixes something we override. Editing the validation shapes or updating the pinned copy changes nothing here until that build is
re-run.

This module also holds what the preflight needs besides the shapes: the per-parameter value shapes of SPARQL-based constraint
components (``parameter_value_shapes``) and the checks of the SPARQL text a shapes graph embeds (``sparql_query_problems``).
"""

from __future__ import annotations

import re
from collections import OrderedDict
from collections.abc import Iterable, Iterator
from typing import Any

import pyoxigraph as ox

from starlayer.shacl.engine.graphs import new_graph
from starlayer.shacl.engine.meta_scope import MetaScope
from starlayer.shacl.engine.terms import (
    RDF,
    SH,
    XSD,
    engine_view,
    integer,
    text,
    to_engine,
)

# sparql_query_problems()'s own sqe structural-validation result cache: validating an encoded query is a real SHACL
# validation pass, not cheap, and otherwise uncached. Keyed directly on the exact inputs that determine its result
# (predicate, the literal query text, and its resolved prefix map), which are already directly, stably hashable. Same bounded-LRU
# shape as _META_VALIDATE_CACHE, kept as a separate cache since it's keyed on different things (one query's text+prefixes, not a
# whole shapes graph's content).
_SPARQL_STRUCTURE_CACHE_MAXSIZE = 256
_SPARQL_STRUCTURE_CACHE: OrderedDict[tuple, tuple] = OrderedDict()



def parameter_value_shapes(shapes_graph: Any) -> Any:
    """Shapes that check what a shapes graph gives for the parameters of its constraint components, as an ``StarLayerGraph``.

    SPARQL Extensions 4.2.1: "Shapes that do not conform with the constraints declared for the parameters are ill-formed." A parameter
    of a ``sh:ConstraintComponent`` is a property shape (``sh:datatype``, ``sh:nodeKind``, ``sh:class``, ``sh:in``, ...) for the values a
    shape gives that property. This returns a graph holding each such parameter as a property shape that targets the subjects of its
    ``sh:path``, so validating ``shapes_graph`` against it (alone or added to the meta-shapes) reports a shape whose value for the property
    breaks the parameter's own constraints, for example text given for an ``xsd:integer`` parameter. The engine does not check this: a
    query comparing text with a number silently finds nothing.

    Only a parameter whose path is an IRI is used; the parameter's own triples (and what hangs from its blank nodes) are copied, so the
    returned graph shares no blank node with ``shapes_graph`` beyond the parameter's own label.
    """
    from starlayer.shacl.engine.sparql_support import is_true

    shapes_graph = engine_view(shapes_graph, "shapes graph")
    out: list[tuple[Any, Any, Any]] = []

    def copy_constraints(parameter: Any) -> None:
        pending, seen = [parameter], set()
        while pending:
            node = pending.pop()
            if node in seen:
                continue
            seen.add(node)
            for s_, p_, o_ in shapes_graph.triples((node, None, None)):
                if p_ in (SH.optional, SH.keyParameter, SH.name, SH.description, SH.order, SH.group):
                    continue  # (what a parameter says about itself, not a constraint on its values)
                out.append((s_, p_, o_))
                if isinstance(o_, ox.BlankNode):
                    pending.append(o_)
        out.append((parameter, RDF.type, SH.PropertyShape))

    def iri_paths(parameter: Any) -> list[Any]:
        return [p for p in shapes_graph.objects(parameter, SH.path) if isinstance(p, ox.NamedNode)]

    components = set(shapes_graph.subjects(RDF.type, SH.ConstraintComponent))
    for component in components:
        for parameter in shapes_graph.objects(component, SH.parameter):
            paths = iri_paths(parameter)
            if len(paths) != 1:
                continue
            copy_constraints(parameter)
            out.append((parameter, SH.targetSubjectsOf, paths[0]))

    # A rule template (Inference Rules 12): its instances give each parameter as a property. The values must satisfy the parameter's own
    # constraints (a violation); an instance takes one value of each (a violation) and needs one of each required parameter (a warning: an
    # instance is typed before its values are given, so a missing value must not refuse the edit that is half way there).
    for template in set(shapes_graph.subjects(RDF.type, SH.SPARQLRuleTemplate)):
        instance_shape = ox.BlankNode()
        out.append((instance_shape, RDF.type, SH.NodeShape))
        out.append((instance_shape, SH.targetClass, template))
        for parameter in shapes_graph.objects(template, SH.parameter):
            paths = iri_paths(parameter)
            if len(paths) != 1:
                continue
            copy_constraints(parameter)
            out.append((instance_shape, SH.property, parameter))
            at_most = ox.BlankNode()
            out.append((instance_shape, SH.property, at_most))
            out.append((at_most, SH.path, paths[0]))
            out.append((at_most, SH.maxCount, integer(1)))
            out.append((at_most, SH.message, ox.Literal(f"An instance of {text(template)} takes one value of {text(paths[0])}.", language="en")))
            if not any(isinstance(v, ox.Literal) and is_true(v) for v in shapes_graph.objects(parameter, SH.optional)):
                required = ox.BlankNode()
                out.append((instance_shape, SH.property, required))
                out.append((required, SH.path, paths[0]))
                out.append((required, SH.minCount, integer(1)))
                out.append((required, SH.severity, SH.Warning))
                out.append((required, SH.message, ox.Literal(f"An instance of {text(template)} needs a value of {text(paths[0])}.", language="en")))

    # A template's query is run with each parameter bound as a variable named after the local name of its path; $this is the focus node. A variable
    # the query builds a triple from that neither the parameters nor its own pattern bind is never bound, so the rule infers nothing (a warning).
    for template in sorted(set(shapes_graph.subjects(RDF.type, SH.SPARQLRuleTemplate)), key=text):
        unbound = _template_unbound_variables(shapes_graph, template)
        if unbound:
            warn = ox.BlankNode()
            out.append((warn, RDF.type, SH.NodeShape))
            out.append((warn, SH.targetNode, template))
            empty = ox.BlankNode()
            out.append((warn, SH["not"], empty))
            out.append((empty, RDF.type, SH.NodeShape))   # (an empty shape always holds, so its negation never does: the warning is reported on the template)
            out.append((warn, SH.severity, SH.Warning))
            names = ", ".join("$" + name for name in unbound)
            out.append((warn, SH.message, ox.Literal(f"The query builds triples from {names}, which no parameter binds and its pattern does not, so no triple is made from it.", language="en")))
    result = new_graph()
    result.extend(out)
    return result


def _template_unbound_variables(shapes_graph: Any, template: Any) -> list[str]:
    """The variables a rule template's ``sh:construct`` builds triples from that nothing binds: not a parameter (its path's local name), not ``this``, and not in
    the query's own pattern. Empty when the query does not parse (that is reported elsewhere) or the template has no single query."""
    from starlayer.sparql.parse_sparql import _pattern_vars, _term_vars

    texts = [t.value for t in shapes_graph.objects(template, SH.construct) if isinstance(t, ox.Literal)]
    if len(texts) != 1:
        return []
    try:
        ast = _parse_embedded_query(texts[0], {**{p: ns for p, ns in shapes_graph.namespaces() if p}, **_collect_query_prefixes(shapes_graph, template)})
        if ast.kind != "ConstructQuery":
            return []
        used_vars: set = set()
        for triple in ast.f["template"] or []:
            for part in ("s", "p", "o"):
                _term_vars(triple.f[part], used_vars)
        used = {v.value for v in used_vars}
        bound = {v.value for v in _pattern_vars(ast.f["where"])}
    except Exception:  # noqa: BLE001 - a query that cannot be read is reported by sparql_query_problems
        return []
    local = lambda iri: re.split(r"[#/]", text(iri))[-1]  # noqa: E731
    parameters = {local(path) for parameter in shapes_graph.objects(template, SH.parameter) for path in shapes_graph.objects(parameter, SH.path)}
    return sorted(used - bound - parameters - {"this"})


def load_meta_shapes_graph(extra_graphs: Iterable[Any] = ()) -> Any:
    """The meta-shapes graph ``meta_validate()`` checks against, read from
    the stored ``shacl12-shacl.ttl`` (``starontology``'s ``"shacl_shacl"``
    entry) rather than reassembled from the Working Group's meta-shapes and
    starShacl's additions on every call.

    The stored file is built by ``scripts/build_meta_shapes.py`` (run through
    ``scripts/build_starontology.py``); it is the authoritative copy at run
    time, so editing the validation shapes or the pinned Working Group file has
    no effect on validation until the file is regenerated. A test compares the stored
    file with a fresh build and fails on drift.

    The private layer ``shacl_shacl_starlayer`` (the two checks that call StarLayer-internal SPARQL functions) is merged in; ``shacl_shacl`` alone
    holds only standard SHACL and SPARQL. The files are parsed once per process by ``starontology`` and cached there;
    each call returns a fresh ``StarLayerGraph`` copy, so ``extra_graphs`` can be added (plain
    triple addition) without affecting later calls.
    """
    # Lazy: starontology must finish importing before this module reads it.
    from starlayer import starontology

    stored = starontology.get_ontology_graph("shacl_shacl")
    graph = new_graph(stored)
    graph.extend(list(stored.triples((None, None, None))))
    # The layer of shapes that call StarLayer's own SPARQL functions; shacl_shacl alone stays standard SHACL and SPARQL.
    graph.extend(list(starontology._load_private("shacl_shacl_starlayer").triples((None, None, None))))
    for extra in extra_graphs:
        triples = engine_view(extra, "extra meta-shapes graph").triples((None, None, None)) if hasattr(extra, "triples") else extra
        graph.extend([tuple(to_engine(x) for x in triple) for triple in triples])
    return graph




def meta_validate(
    shapes_graph: Any,
    *,
    add: Iterable[Any] = (),
    remove: Iterable[Any] = (),
    full: bool = False,
    extra_graphs: Iterable[Any] = (),
) -> tuple[bool, Any, str]:
    """Validate ``shapes_graph`` against the meta-shapes graph (see ``load_meta_shapes_graph``) with the engine.

    Returns ``(conforms, report_graph, report_text)`` and raises ``MetaShaclError`` (message starting "The shapes graph is not valid SHACL",
    then one line per problem naming the shape, the property and what is wrong; ``problems``, ``report_text`` and ``scope`` hold the same) when the
    shapes graph does not conform. There is no way to tolerate a warning or an info result: the meta check is strict, whatever a
    processor's ``allow_warnings`` / ``allow_infos`` say (those are for the data validation), because SHACL 1.2 Core's default set
    (Violation, Warning, Info) makes any of them a non-conforming report and the W3C SHACL-for-SHACL says to deactivate a Warning shape
    if a use case needs the construct, not to ignore it; pySHACL's meta check is strict too. The results of every severity are in the
    error's ``report_graph``, so an editor can still show a warning on its own. ``extra_graphs`` are added to the meta-shapes. The report is
    an ``StarLayerGraph``.

    ``add`` and ``remove`` (triples) propose an edit that is checked before it is made: the check runs on the graph as it would be
    after the edit and ``shapes_graph`` is not changed. The library chooses the extent itself, a fraction of a second against seconds
    for a large graph: the nodes the edit touches, their inline blank nodes and the shapes that refer to them, or the whole graph when
    the edit can change what other nodes mean (prefix declarations, components, rule templates, the type of an existing node).
    ``full=True`` overrides that choice and checks the whole graph as it would be after the edit; a narrow check is for use between
    edits, and the full check is the one to run before the shapes are saved or published. ``meta_scope`` says what an edit covers."""
    from starlayer.shacl.engine.meta import meta_validate as engine_meta_validate

    result = engine_meta_validate(shapes_graph, extra=extra_graphs, add=add, remove=remove, full=full)
    result.raise_if_invalid()
    return result.conforms, result.report_graph, result.report_text


def meta_scope(
    shapes_graph: Any,
    *,
    add: Iterable[Any] = (),
    remove: Iterable[Any] = (),
    full: bool = False,
) -> MetaScope:
    """What ``meta_validate`` with the same arguments covers and why, as a ``MetaScope``: ``full`` (the edit is one that other nodes
    inherit from, ``full=True`` was passed, or no edit was given), the focus ``nodes`` and ``reasons``. It does not validate or copy
    anything (a few milliseconds on thousands of shapes), so an editor can show it next to a valid result, which has no error to carry it."""
    from starlayer.shacl.engine.meta import meta_scope as engine_meta_scope

    return engine_meta_scope(shapes_graph, add=add, remove=remove, full=full)


def _collect_query_prefixes(shapes_graph: Any, query_node: Any) -> dict[str, str]:
    """Resolve the prefix map a ``sh:select``/``sh:ask``/``sh:construct``
    query at ``query_node`` would actually see at real execution time -
    the engine's own
    ``sparql_support.prefixes_of`` (``sh:prefixes`` with its ``owl:imports`` closure, or the ``sh:ShapesGraph`` / ontology
    declarations when there is no ``sh:prefixes``) on a plain shapes graph.

    Only ``sh:prefixes`` / ``sh:declare`` declare prefixes (SHACL SPARQL Extensions); there is no ambient lookup, not even for ``rdf:``,
    ``rdfs:`` and ``owl:``: the engine binds none when it runs the query, so a check that assumed them would pass what then fails.
    """
    prefixes: dict[str, str] = {}

    from starlayer.shacl.engine.plan import ShapeError
    from starlayer.shacl.engine.sparql_support import prefixes_of

    try:
        prefixes.update(prefixes_of(shapes_graph, query_node))
    except ShapeError:  # a malformed declaration is reported by the meta-shapes, not here
        pass
    return prefixes


# SHACL-SPARQL's own pre-bound pseudo-variables are supplied externally by
# pySHACL's own execution machinery before a sh:select/sh:ask/sh:construct
# query ever runs - never by anything in the query's own WHERE pattern -
# for a CONSTRAINT or RULE query. the sqe: unbound-variable checks (a
# plain, SHACL-unaware generic SPARQL check) has no way to know this, so
# without this exemption it would flag every single `$this`-only validator
# (an extremely common, perfectly valid pattern - e.g.
# `SELECT $this WHERE { FILTER(...) }`, with nothing in the pattern ever
# referencing $this directly) as a false positive - confirmed live via a
# real such query. Matches this function's own pre-existing docstring note
# on these three names (the parse check already didn't need to
# special-case them; the structural check does).
#
# (SPARQL-based targets, where $this is computed by the query, are not defined in SHACL 1.2 and are refused by the meta-shapes.)
_SHACL_PREBOUND_VARIABLE_NAMES = frozenset({"this", "value", "PATH", "currentShape", "shapesGraph"})

_VALIDATOR_PREDICATES = (SH.validator, SH.nodeValidator, SH.propertyValidator)


def _declared_parameter_names(shapes_graph: Any, query_node: Any) -> frozenset[str]:
    """The variables the engine pre-binds for ``query_node`` because its owner declares ``sh:parameter``s (SHACL-SPARQL, constraint
    components: each parameter's path local name): the parameters of a component that has the node as a validator, and the node's own
    (a rule template). Only the owner's: another component's parameters are not bound."""
    owners = [query_node]
    for predicate in _VALIDATOR_PREDICATES:
        owners.extend(shapes_graph.subjects(predicate, query_node))
    names: set[str] = set()
    for owner in owners:
        for parameter in shapes_graph.objects(owner, SH.parameter):
            for path in shapes_graph.objects(parameter, SH.path):
                if isinstance(path, ox.NamedNode):
                    names.add(re.split(r"[#/]", path.value)[-1])
    return frozenset(names)


_UNBOUND_VARIABLE_MESSAGE = re.compile(r"^(?:Projected variable|Template variable|Variable) (\S+) (?:is never bound|is used inside an expression)")


def _is_prebound_variable_only_report(report_graph: Any, extra: frozenset[str] = frozenset(), base: frozenset[str] = _SHACL_PREBOUND_VARIABLE_NAMES) -> bool:
    """True iff every violation in an ``sqe_validate()`` report is an unbound-variable hit naming only a SHACL pre-bound
    pseudo-variable (``$this``/``$value``/``$PATH``/``$currentShape``/``$shapesGraph``, or a declared parameter in ``extra``) - a false positive this check should suppress, not a real defect. The
    variable is read from the result message the ``sqe:`` shapes write ("Projected variable this is never bound ...").
    ``extra`` adds names that are bound some other way (for ``shui:searchQuery``: ``$searchTerm`` and ``$language``, which the renderer
    substitutes before it runs the query).
    ``False`` (never suppressed) for an empty result set too - that would mean ``conforms`` was already ``True`` and there was
    nothing to call this for in the first place.
    """
    report_graph = engine_view(report_graph, "sqe report")
    results = list(report_graph.subjects(RDF.type, SH.ValidationResult))
    if not results:
        return False
    for result in results:
        message = report_graph.value(result, SH.resultMessage)
        match = _UNBOUND_VARIABLE_MESSAGE.match(text(message)) if message is not None else None
        if match is None or match.group(1) not in base | extra:
            return False
    return True


def _parse_embedded_query(query_text: str, prefixes: dict[str, str]) -> Any:
    """The parse tree of the SPARQL text embedded in a shapes graph, with ``prefixes`` in force."""
    from starlayer.sparql.parse_sparql import parse_sparql

    return parse_sparql(query_text, None, prefixes)


# shui:searchQuery (SHACL UI, Search Query): a SELECT with at least one projected variable (the parser requires a projection or *), on a
# property shape, with the prefixes of sh:declare / sh:prefixes like any embedded query. The $searchTerm and $language it uses are
# ordinary variables of the text; the renderer substitutes them before it runs the query.
SHUI_SEARCH_QUERY = ox.NamedNode("http://www.w3.org/ns/shacl-ui/searchQuery")
_SEARCH_QUERY_PLACEHOLDERS = frozenset({"searchTerm", "language"})
_QUERY_FORMS = {
    SH.select: ("SelectQuery", "SELECT"),
    SH.ask: ("AskQuery", "ASK"),
    SH.construct: ("ConstructQuery", "CONSTRUCT"),
    SHUI_SEARCH_QUERY: ("SelectQuery", "SELECT"),
}
_QUERY_NAMES = {SH.select: "sh:select", SH.ask: "sh:ask", SH.construct: "sh:construct", SHUI_SEARCH_QUERY: "shui:searchQuery"}


# What the engine refuses in a query of the SHACL SPARQL Extensions, by where the query is used and which predicate holds it:
# (pre-bound variables, whether MINUS, VALUES and assignment are limited, whether a SELECT must project ?this). The engine checks a query when it runs it,
# with the variables it has bound: ``?this`` always, ``?value`` for the ASK of a validator; a variable of a parameter only when the parameter has a value, which
# a shapes graph alone does not say, so those are left out (a check that can only miss, never refuse what the engine accepts). A global rule has no pre-binding.
# A node expression's SELECT is run with the variables of its scope, so only SERVICE and MINUS, which are refused whatever is bound, are checked there.
_RESTRICTIONS: dict[tuple[str, Any], tuple[tuple[str, ...], bool, bool]] = {
    ("constraint", SH.select): (("this",), True, True),
    ("validator", SH.select): (("this",), True, True),
    ("validator", SH.ask): (("this", "value"), True, False),
    ("rule", SH.construct): (("this",), True, False),
    ("global-rule", SH.construct): ((), False, False),
    ("expression", SH.select): ((), True, False),
}


_SUBCLASS_OF = ox.NamedNode("http://www.w3.org/2000/01/rdf-schema#subClassOf")


def _is_deactivated(shapes_graph: Any, node: Any) -> bool:
    return any(isinstance(d, ox.Literal) and d.datatype == XSD.boolean and d.value in ("true", "1") for d in shapes_graph.objects(node, SH.deactivated))


def query_context(shapes_graph: Any, node: Any) -> str:
    """Where the query held by ``node`` is run, which says what the engine refuses in it: ``"inactive"`` (``sh:deactivated true``, never run), ``"constraint"``
    (the value of ``sh:sparql`` of a shape that is not deactivated), ``"validator"`` (of a constraint component), ``"rule"`` (a rule of a shape that is not
    deactivated, or a template with such a rule), ``"global-rule"`` (a rule no shape holds), ``"expression"`` (a blank node something refers to: a node expression)
    or ``"none"``. ``stsh:SPARQLQueryTextShape`` works this out in SPARQL; the two are kept the same by ``tests/shacl/integration/test_meta_sparql_restrictions.py``."""
    if _is_deactivated(shapes_graph, node):
        return "inactive"
    if any(not _is_deactivated(shapes_graph, shape) for shape in shapes_graph.subjects(SH.sparql, node)):
        return "constraint"
    if any(next(iter(shapes_graph.subjects(predicate, node)), None) is not None for predicate in _VALIDATOR_PREDICATES):
        return "validator"
    classes, queue = {node}, [node]
    while queue:
        for sub in shapes_graph.subjects(_SUBCLASS_OF, queue.pop()):
            if sub not in classes:
                classes.add(sub)
                queue.append(sub)
    rules = {node} | {rule for cls in classes for rule in shapes_graph.subjects(RDF.type, cls)}
    if any(not _is_deactivated(shapes_graph, shape) for rule in rules for shape in shapes_graph.subjects(SH.rule, rule)):
        return "rule"
    if SH.SPARQLRule in set(shapes_graph.objects(node, RDF.type)) or len(rules) > 1:
        return "global-rule"
    if isinstance(node, ox.BlankNode) and next(iter(shapes_graph.triples((None, None, node))), None) is not None:
        return "expression"
    return "none"


def sparql_text_problem(predicate: Any, query_text: str, prefixes: dict[str, str], declared: frozenset[str] = frozenset(), context: str = "none") -> str | None:
    """What is wrong with one embedded query, or None: text that is not SPARQL, a query of another form than ``predicate`` says (a SELECT in
    ``sh:construct``), one that fails the SPARQL structure check, or one the engine refuses to run where it is used (``context``, see ``query_context``): a
    SERVICE, a MINUS, a VALUES or an assignment of a variable that is pre-bound there, a SELECT that does not project ``?this``. The last group is the engine's own
    check (``engine/sparql_support.restriction_problem``). This is the verdict of ``stsh:sparqlProblem`` (``engine/builtin_functions.py``) and of
    ``sparql_query_problems``, so the shapes of ``shacl_shacl_starlayer`` and a tool that lists problems cannot disagree."""
    from starlayer.sparql.parse_sparql import SparqlSyntaxError, ast_to_triples
    from starlayer.sparql.sqe.shapes import sqe_validate

    name = _QUERY_NAMES[predicate]
    try:
        query = _parse_embedded_query(query_text, prefixes)
    except (SparqlSyntaxError, ValueError) as exc:
        return f"{name} value is not valid SPARQL: {exc}"
    algebra_name, form = _QUERY_FORMS[predicate]
    if query.kind != algebra_name:
        actual = next((f for n, f in _QUERY_FORMS.values() if n == query.kind), query.kind)
        return f"{name} must hold a {form} query, but this is a {actual} query"
    cache_key = (predicate, query_text, tuple(sorted(prefixes.items())), tuple(sorted(declared)))
    cached = _SPARQL_STRUCTURE_CACHE.get(cache_key)
    if cached is not None:
        conforms, report_text = cached
    else:
        from starlayer.graph.core import StarLayerGraph

        encoded_graph = StarLayerGraph(prefixes={})
        encoded_graph.extend(ast_to_triples(query)[0])
        conforms, report_graph, report_text = sqe_validate(encoded_graph)
        bound = declared | (_SEARCH_QUERY_PLACEHOLDERS if predicate == SHUI_SEARCH_QUERY else frozenset())
        if not conforms and _is_prebound_variable_only_report(report_graph, bound, _SHACL_PREBOUND_VARIABLE_NAMES):
            conforms = True
        _SPARQL_STRUCTURE_CACHE[cache_key] = (conforms, report_text)
        _SPARQL_STRUCTURE_CACHE.move_to_end(cache_key)
        if len(_SPARQL_STRUCTURE_CACHE) > _SPARQL_STRUCTURE_CACHE_MAXSIZE:
            _SPARQL_STRUCTURE_CACHE.popitem(last=False)
    if not conforms:
        return f"{name} value fails SPARQL structural validation:\n{report_text}"
    restriction = _RESTRICTIONS.get((context, predicate))
    if restriction is None:
        return None
    from starlayer.shacl.engine.sparql_support import restriction_problem

    prebound, pre_binding, require_this = restriction
    header = "".join(f"PREFIX {prefix}: <{namespace}>\n" for prefix, namespace in prefixes.items())  # str-ok: prefix and namespace strings, as the engine writes them
    return restriction_problem(header + query_text, prebound, pre_binding=pre_binding, require_this=require_this)


def sparql_query_problems(shapes_graph: Any) -> Iterator[tuple[Any, Any, str]]:
    """Each defect of an embedded query as ``(the node that holds it, sh:select/sh:ask/sh:construct/shui:searchQuery, what is wrong)``, read straight from
    the graph with ``sparql_text_problem``. ``meta_validate`` gets the same defects from the ``shacl_shacl_starlayer`` shapes; this is for a tool that has no report to read."""
    shapes_graph = engine_view(shapes_graph, "shapes graph")
    for predicate in _QUERY_FORMS:
        for query_node, text_literal in shapes_graph.subject_objects(predicate):
            if not isinstance(text_literal, ox.Literal) or not (text_literal.language or text_literal.datatype == XSD.string):
                continue  # not xsd:string - already caught by the meta-shapes structural check
            # Only sh:declare / sh:prefixes, as the engine does: a prefix the file merely binds (@prefix) is not resolved at run time.
            problem = sparql_text_problem(predicate, text_literal.value, _collect_query_prefixes(shapes_graph, query_node),
                                          _declared_parameter_names(shapes_graph, query_node), query_context(shapes_graph, query_node))
            if problem:
                yield query_node, predicate, problem
