"""The meta-SHACL preflight: a shapes graph checked against SHACL-for-SHACL before it is used (``meta_shacl=True``).

The meta-shapes graph is not assembled at run time. It is stored as ``starontology``'s ``shacl12-shacl.ttl`` (registry entry
``shacl_shacl``) and read by ``load_meta_shapes_graph``; ``starlayer.shacl_engine.meta`` runs the check. The build that produces
the stored graph lives in ``scripts/build_meta_shapes.py`` and is run by ``scripts/build_starontology.py``. It starts from the W3C
Data Shapes Working Group's own SHACL-for-SHACL (a pinned copy, ``scripts/assets/vendor/w3c-shacl-shacl.ttl``) and only adds to
it: ``shacl12-validation-shapes.ttl`` plus ``sh:deactivated`` on the few Working Group rules that are still stricter than
SHACL 1.2. A test fails if the stored file drifts from a fresh build, and ``test_wg_overrides.py`` fails when the Working Group
fixes something we override. Editing the validation shapes or updating the pinned copy changes nothing here until that build is
re-run.

This module also holds what the preflight needs besides the shapes: the per-parameter value shapes of SPARQL-based constraint
components (``parameter_value_shapes``) and the checks of the SPARQL text a shapes graph embeds (``check_sparql_query_text``,
``sparql_query_problems``).
"""

from __future__ import annotations

import re
from collections import OrderedDict
from collections.abc import Iterable, Iterator
from typing import Any

import pyoxigraph as ox

from starlayer.shacl_engine.graphs import new_graph
from starlayer.shacl_engine.terms import (
    OWL,
    RDF,
    SH,
    XSD,
    engine_view,
    integer,
    text,
    to_engine,
)

# check_sparql_query_text()'s own SALG structural-validation result cache -
# salg.validate_query() is a real pySHACL validation pass (shapes/ontology
# graphs rebuilt from Turtle each call, RDFS inference enabled), not cheap,
# and otherwise uncached. Keyed directly on the exact inputs that determine
# its result (predicate, the literal query text, and its resolved prefix
# map) - no graph-identity/blank-node concern here the way
# _meta_validate_cache_key has, so no rdfc10_hash needed; these values are
# already directly, stably hashable. Same bounded-LRU shape as
# _META_VALIDATE_CACHE, kept as a separate cache since it's keyed on
# different things (one query's text+prefixes, not a whole shapes graph's
# content).
_SPARQL_STRUCTURE_CACHE_MAXSIZE = 256
_SPARQL_STRUCTURE_CACHE: OrderedDict[tuple, tuple] = OrderedDict()



def parameter_value_shapes(shapes_graph: Any) -> Any:
    """Shapes that check what a shapes graph gives for the parameters of its constraint components, as an ``OxGraph``.

    SPARQL Extensions 4.2.1: "Shapes that do not conform with the constraints declared for the parameters are ill-formed." A parameter
    of a ``sh:ConstraintComponent`` is a property shape (``sh:datatype``, ``sh:nodeKind``, ``sh:class``, ``sh:in``, ...) for the values a
    shape gives that property. This returns a graph holding each such parameter as a property shape that targets the subjects of its
    ``sh:path``, so validating ``shapes_graph`` against it (alone or added to the meta-shapes) reports a shape whose value for the property
    breaks the parameter's own constraints, for example text given for an ``xsd:integer`` parameter. The engine does not check this: a
    query comparing text with a number silently finds nothing.

    Only a parameter whose path is an IRI is used; the parameter's own triples (and what hangs from its blank nodes) are copied, so the
    returned graph shares no blank node with ``shapes_graph`` beyond the parameter's own label.
    """
    from starlayer.shacl_engine.sparql_support import is_true

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
    import starlayer.sparql

    texts = [t.value for t in shapes_graph.objects(template, SH.construct) if isinstance(t, ox.Literal)]
    if len(texts) != 1:
        return []
    try:
        query = starlayer.sparql.prepare_query_12(texts[0], initNs={**{p: ns for p, ns in shapes_graph.namespaces() if p}, **_collect_query_prefixes(shapes_graph, template)})
        algebra = query.algebra
        if algebra.name != "ConstructQuery":
            return []
        used = {str(term) for triple in algebra.template for term in triple if type(term).__name__ == "Variable"}
        bound = {str(v) for v in getattr(algebra.p, "_vars", ())}
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

    The file is parsed once per process by ``starontology`` and cached there;
    each call returns a fresh ``OxGraph`` copy, so ``extra_graphs`` can be added (plain
    triple addition) without affecting later calls.
    """
    # Lazy: starontology must finish importing before this module reads it.
    from starlayer import starontology

    stored = starontology.get_ontology_graph("shacl_shacl")
    graph = new_graph(stored)
    graph.extend(list(stored.triples((None, None, None))))
    for extra in extra_graphs:
        triples = engine_view(extra, "extra meta-shapes graph").triples((None, None, None)) if hasattr(extra, "triples") else extra
        graph.extend([tuple(to_engine(x) for x in triple) for triple in triples])
    return graph




def meta_validate(shapes_graph: Any, *, extra_graphs: Iterable[Any] = (), **kwargs: Any) -> tuple[bool, Any, str]:
    """Validate ``shapes_graph`` against the meta-shapes graph (see ``load_meta_shapes_graph``) with the engine.

    Returns ``(conforms, report_graph, report_text)`` and raises ``MetaShaclError`` (message starting "SHACL File does not validate
    against the SHACL Shapes SHACL (MetaSHACL) file.") when the shapes graph does not conform. A warning-severity meta-shape is
    advice: it appears in the report but does not make the graph invalid (``allow_warnings=True``; pass ``allow_warnings=False`` to
    count warnings, ``allow_infos=True`` to tolerate infos only). ``extra_graphs`` are added to the meta-shapes. The report is
    an ``OxGraph``."""
    from starlayer.shacl_engine.meta import meta_validate as engine_meta_validate

    result = engine_meta_validate(
        shapes_graph,
        extra=extra_graphs,
        allow_warnings=kwargs.pop("allow_warnings", True),
        allow_infos=kwargs.pop("allow_infos", None),
    )
    if kwargs:
        raise TypeError(f"unknown option(s) {', '.join(sorted(kwargs))}")
    result.raise_if_invalid()
    return result.conforms, result.report_graph, result.report_text


def _collect_query_prefixes(shapes_graph: Any, query_node: Any) -> dict[str, str]:
    """Resolve the prefix map a ``sh:select``/``sh:ask``/``sh:construct``
    query at ``query_node`` would actually see at real execution time -
    same algorithm as pySHACL's own
    ``SPARQLQueryHelper.collect_prefixes()``, reimplemented directly
    against a plain shapes graph rather than through a full ``Shape``/
    ``pyshacl.ShapesGraph`` wrapper (unnecessary overhead for a read-only prefix
    lookup - ``shape.sg.graph`` is just the same graph passed in here).

    Only ``sh:prefixes`` / ``sh:declare`` declare prefixes (SHACL SPARQL Extensions); there is no ambient lookup.
    """
    prefixes: dict[str, str] = {
        "rdf": "http://www.w3.org/1999/02/22-rdf-syntax-ns#",
        "rdfs": "http://www.w3.org/2000/01/rdf-schema#",
        "owl": "http://www.w3.org/2002/07/owl#",
    }

    prefixes_vals = set(shapes_graph.objects(query_node, SH.prefixes))
    if not prefixes_vals:
        return prefixes

    g_name = getattr(shapes_graph, "identifier", None)
    ng_declares = set(shapes_graph.objects(g_name, SH.declare)) if g_name is not None else set()
    onts = set(shapes_graph.subjects(RDF.type, OWL.Ontology))
    ont_declares: set = set()
    for o in onts:
        ont_declares.update(shapes_graph.objects(o, SH.declare))
    global_declares = ng_declares | ont_declares

    for pv in prefixes_vals:
        pfx_declares = set(shapes_graph.objects(pv, SH.declare))
        all_declares = (pfx_declares | ng_declares) if (pfx_declares and pv in onts) else (global_declares | pfx_declares)
        for dec in all_declares:
            prefix_vals = list(shapes_graph.objects(dec, SH.prefix))
            ns_vals = list(shapes_graph.objects(dec, SH.namespace))
            if len(prefix_vals) == 1 and len(ns_vals) == 1:
                prefixes[text(prefix_vals[0])] = text(ns_vals[0])
    return prefixes


def _sparql_structure_cache_key(predicate: Any, text_literal: Any, prefixes: dict, is_target: bool) -> tuple:
    """Cache key for one query's structural-validation outcome - the exact
    inputs the *effective* (exemption-applied) result depends on for this
    one embedded query: which predicate carried it (part of the error
    message, not the semantics, but cheap to include and keeps the key
    unambiguous), the literal text itself, its resolved prefix map (two
    otherwise-identical query strings can mean different things under
    different prefix bindings), and ``is_target`` - whether ``$this`` is
    genuinely required to be bound by this query's own pattern (a
    ``sh:target``-declared SPARQL target) or externally pre-bound (every
    other case) changes whether a given unbound-``$this`` violation is a
    real defect, even for byte-identical query text (see
    ``_is_prebound_variable_only_report``'s own docstring).
    """
    return (
        predicate,
        text(text_literal),
        tuple(sorted(prefixes.items())),
        is_target,
    )


# SHACL-SPARQL's own pre-bound pseudo-variables are supplied externally by
# pySHACL's own execution machinery before a sh:select/sh:ask/sh:construct
# query ever runs - never by anything in the query's own WHERE pattern -
# for a CONSTRAINT or RULE query. salg:noUnboundProjectedVariables (a
# plain, SHACL-unaware generic SPARQL check) has no way to know this, so
# without this exemption it would flag every single `$this`-only validator
# (an extremely common, perfectly valid pattern - e.g.
# `SELECT $this WHERE { FILTER(...) }`, with nothing in the pattern ever
# referencing $this directly) as a false positive - confirmed live via a
# real such query. Matches this function's own pre-existing docstring note
# on these three names (the parse check already didn't need to
# special-case them; the structural check does).
#
# This does NOT hold for a SPARQL-based TARGET (`sh:target [ a
# sh:SPARQLTarget ; sh:select ... ]`) - there, $this is not pre-bound at
# all; it's the query's own job to *compute* which nodes are $this, so an
# unbound $this in a target query is a real defect (the target would never
# select any candidate), not a false positive. Confirmed live: without
# excluding target queries from this exemption, a target query that never
# binds $this silently passed this check. check_sparql_query_text() below
# detects this via `is_target` (whether query_node is itself the object of
# a sh:target triple) and only applies this exemption when it's False.
_SHACL_PREBOUND_VARIABLE_NAMES = frozenset({"this", "value", "PATH"})


def _is_prebound_variable_only_report(report_graph: Any) -> bool:
    """True iff every violation in a ``salg.validate_query()`` report is a
    ``salg:noUnboundProjectedVariables`` hit naming only a SHACL pre-bound
    pseudo-variable (``$this``/``$value``/``$PATH``) - a false positive
    this check should suppress, not a real defect. ``False`` (never
    suppressed) for an empty result set too - that would mean ``conforms``
    was already ``True`` and there was nothing to call this for in the
    first place.
    """
    from starlayer.sparql import SALG

    report_graph = engine_view(report_graph, "SALG report")  # whatever graph class the SPARQL layer returns
    unbound_component = f"{SALG.NoUnboundProjectedVariablesConstraintComponent}"  # str-ok: an IRI of an rdflib Namespace
    results = list(report_graph.subjects(RDF.type, SH.ValidationResult))
    if not results:
        return False
    for result in results:
        component = report_graph.value(result, SH.sourceConstraintComponent)
        if component is None or text(component) != unbound_component:
            return False
        value = report_graph.value(result, SH.value)
        if value is None or text(value).removeprefix("urn:starlayer:variable:") not in _SHACL_PREBOUND_VARIABLE_NAMES:  # a variable is an IRI at the boundary
            return False
    return True


def check_sparql_query_text(shapes_graph: Any) -> None:
    """Preflight: every ``sh:select``/``sh:ask``/``sh:construct`` literal
    anywhere in ``shapes_graph`` must be syntactically valid SPARQL text,
    and must not have a defect a bare parse can't catch - most notably an
    unbound projected variable (a query that compiles and runs, just
    silently never binds one of its own ``SELECT`` variables).

    The meta-shapes graph already checks these structurally (cardinality,
    ``xsd:string`` datatype), but never actually parses the string -
    confirmed live that ``sh:ask "this is not valid SPARQL at all !!!"``
    conforms cleanly under the structural check alone. This is a
    Python-level check, not another SHACL shape, because "is this string
    valid SPARQL" isn't RDF-structural - no shape can express it.

    A literal that parses is additionally encoded as a ``salg:`` (SPARQL-
    algebra-as-RDF) graph and validated against
    ``starlayer.sparql.salg``'s own general-purpose SPARQL-structure
    shapes - which already has a real check for the unbound-projected-
    variable case (``salg:noUnboundProjectedVariables``), just never
    pointed at a SHACL shape's own embedded query text before this. This
    is real extra validation work (pySHACL with RDFS inference, not just a
    parse), so results are cached per distinct (predicate, text, prefixes)
    - repeated calls against the same shapes graph only pay this once per
    distinct embedded query, the same reason ``meta_validate()`` itself
    caches its own, larger structural pass.

    Scans the whole graph for these three predicates directly rather than
    walking ``sh:sparql``/``sh:validator``/``sh:selectValidator``-style
    parent structures individually - ``sh:select``/``sh:ask``/
    ``sh:construct`` are the same predicates regardless of which kind of
    parent node carries them (an ordinary ``sh:sparql`` constraint, or a
    custom ``sh:ConstraintComponent``'s validator node), so one direct
    scan covers every case uniformly.

    ``$this``/``$value``/``$PATH``-style pre-bound variables need no
    special handling for the parse step - they parse as ordinary ``Var``
    tokens regardless of whether they're bound, which only matters at
    execution time. They *do* need special handling for the structural
    step above: ``salg:noUnboundProjectedVariables`` has no SHACL
    awareness, so a perfectly valid ``$this``-only validator (e.g.
    ``SELECT $this WHERE { FILTER(...) }``, never referencing ``$this``
    directly in its own pattern - these variables are bound externally by
    pySHACL itself, not by anything in the query text) would otherwise be
    a false positive - confirmed live. See
    ``_is_prebound_variable_only_report``'s own docstring for exactly
    which violations this suppresses (only ones naming exactly one of
    these three pre-bound names; anything else still raises). Prefixes do
    matter at parse time (an unresolved ``PrefixedName`` is a real parse
    error), so each query's prefix map is resolved the same way real
    execution would (see ``_collect_query_prefixes``).

    Args:
        shapes_graph: The shapes graph to scan.

    Raises ``ShapeError`` naming the offending predicate and the underlying parse error, or the SALG structural-validation report.
    """
    from starlayer.shacl.errors import ShapeError

    for _node, _predicate, message in sparql_query_problems(shapes_graph):
        raise ShapeError(message)


_QUERY_FORMS = {SH.select: ("SelectQuery", "SELECT"), SH.ask: ("AskQuery", "ASK"), SH.construct: ("ConstructQuery", "CONSTRUCT")}


def sparql_query_problems(shapes_graph: Any) -> Iterator[tuple[Any, Any, str]]:
    """Each defect of an embedded query as ``(the node that holds it, sh:select/sh:ask/sh:construct, what is wrong)``: text that is not SPARQL,
    a query of another form than the predicate says (a SELECT in ``sh:construct``), or one that fails the SPARQL structure check (see
    ``check_sparql_query_text``, which raises the first). A tool shows these next to the other problems of a shapes graph."""
    import starlayer.sparql
    from starlayer.sparql import salg

    shapes_graph = engine_view(shapes_graph, "shapes graph")
    for predicate in (SH.select, SH.ask, SH.construct):
        name = shapes_graph.qname_term(predicate)
        for query_node, text_literal in shapes_graph.subject_objects(predicate):
            if not isinstance(text_literal, ox.Literal) or not (text_literal.language or text_literal.datatype == XSD.string):
                continue  # not xsd:string - already caught by the meta-shapes structural check
            # The engine also resolves a prefix the graph itself binds (a file's @prefix, with no sh:declare), so this does too.
            prefixes = {**{p: ns for p, ns in shapes_graph.namespaces() if p}, **_collect_query_prefixes(shapes_graph, query_node)}
            try:
                query = starlayer.sparql.prepare_query_12(text_literal.value, initNs=prefixes)
            except Exception as exc:
                yield query_node, predicate, f"{name} value is not valid SPARQL: {exc}"
                continue
            algebra_name, form = _QUERY_FORMS[predicate]
            if query.algebra.name != algebra_name:
                actual = next((f for n, f in _QUERY_FORMS.values() if n == query.algebra.name), query.algebra.name)
                yield query_node, predicate, f"{name} must hold a {form} query, but this is a {actual} query"
                continue

            # A sh:target-declared SPARQL target's own $this is NOT
            # pre-bound - it's the query's own job to compute it - so the
            # pre-bound-variable exemption below must not apply to it. See
            # _SHACL_PREBOUND_VARIABLE_NAMES's own comment.
            is_target = any(True for _ in shapes_graph.subjects(SH.target, query_node))
            cache_key = _sparql_structure_cache_key(predicate, text_literal, prefixes, is_target)
            cached = _SPARQL_STRUCTURE_CACHE.get(cache_key)
            if cached is not None:
                conforms, report_text = cached
            else:
                encoded_graph, _root = starlayer.sparql.query_to_rdf(query)
                conforms, report_graph, report_text = salg.validate_query(encoded_graph)
                if not conforms and not is_target and _is_prebound_variable_only_report(report_graph):
                    conforms = True
                _SPARQL_STRUCTURE_CACHE[cache_key] = (conforms, report_text)
                _SPARQL_STRUCTURE_CACHE.move_to_end(cache_key)
                if len(_SPARQL_STRUCTURE_CACHE) > _SPARQL_STRUCTURE_CACHE_MAXSIZE:
                    _SPARQL_STRUCTURE_CACHE.popitem(last=False)
            if not conforms:
                yield query_node, predicate, f"{name} value fails SPARQL structural validation:\n{report_text}"
