"""SPARQL-based constraint components (SHACL 1.2 SPARQL-Related Features, section 4), declared in the shapes graph.

``declared_components(plan)`` reads every ``sh:ConstraintComponent`` (including instances of its ``rdfs:subClassOf``
subclasses) that has ``sh:parameter`` declarations and returns one ``ComponentSpec`` per component, to be added to the
plan's registry. A shape uses a component when it has a value for each non-optional parameter (the parameter's
``sh:path`` is the predicate). Multiple values of a parameter give one evaluation per combination.

Validator choice: node shapes use ``sh:nodeValidator`` else ``sh:validator``; property shapes use
``sh:propertyValidator`` else ``sh:validator``; no validator means the constraint is ignored. An ASK validator runs once
per value node with ``$this`` / ``$value`` pre-bound and a violation when it returns false. A SELECT validator runs once
per focus node, ``$this`` pre-bound (and ``$PATH`` substituted on property shapes). Parameters are pre-bound by the local
name of their path; an absent optional parameter is left unbound. ``sh:labelTemplate`` is not used for results.
"""

from __future__ import annotations

import itertools
import re
from typing import Any

from starlayer.shacl_engine.components.registry import (
    REGISTRY,
    ComponentSpec,
    Violation,
)
from starlayer.shacl_engine.plan import SH, Plan, Shape, ShapeError, Term
from starlayer.shacl_engine.sparql_support import (
    fill_template,
    is_true,
    run_ask,
    run_select,
    substitute_path,
    violations_from_solutions,
    with_prefixes,
)
from starlayer.shacl_engine.terms import RDF, RDFS
from starlayer.shacl_engine.terms import NamedNode as URIRef

_RESERVED = {"this", "path", "PATH", "value", "message", "failure"}
_VARNAME = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


def _subclass_closure(graph: Any, root: Term) -> list[Term]:
    seen: dict = {root: None}
    queue = [root]
    while queue:
        for sub in graph.subjects(RDFS.subClassOf, queue.pop()):
            if sub not in seen:
                seen[sub] = None
                queue.append(sub)
    return list(seen)


def _local_name(iri: Term) -> str:
    return re.split(r"[#/]", iri.value)[-1]


def _parameters(graph: Any, comp: Term, *, allow_all_optional: bool = False) -> list[tuple[URIRef, str, bool]]:
    """(path predicate, variable name, optional) per ``sh:parameter`` of the component, or of a SPARQL rule template, whose
    parameters may all be optional (``allow_all_optional``; a constraint component needs one that is not)."""
    out: list[tuple[URIRef, str, bool]] = []
    for param in graph.objects(comp, SH.parameter):
        paths = list(graph.objects(param, SH.path))
        if len(paths) != 1 or not isinstance(paths[0], URIRef):
            raise ShapeError(f"{param!r}: a parameter needs exactly one IRI sh:path")
        name = _local_name(paths[0])
        if not _VARNAME.match(name) or name in _RESERVED:
            raise ShapeError(f"{param!r}: {name!r} is not a usable parameter name")
        optionals = list(graph.objects(param, SH.optional))
        if len(optionals) > 1:
            raise ShapeError(f"{param!r}: more than one sh:optional")
        out.append((paths[0], name, bool(optionals) and is_true(optionals[0])))
    if len({n for _p, n, _o in out}) != len(out):
        raise ShapeError(f"{comp!r}: two parameters have the same name")
    if out and all(opt for _p, _n, opt in out) and not allow_all_optional:
        raise ShapeError(f"{comp!r}: a constraint component needs at least one non-optional parameter")
    return out


def _validator(graph: Any, comp: Term, shape: Shape) -> Term | None:
    first = SH.propertyValidator if shape.is_property else SH.nodeValidator
    for pred in (first, SH.validator):
        found = list(graph.objects(comp, pred))
        if found:
            return found[0]
    return None


def _make_fn(comp: Term, params: list[tuple[URIRef, str, bool]]):
    def fn(ctx, shape: Shape, present, focus: Term, values: tuple):
        graph = ctx.shapes
        validator = _validator(graph, comp, shape)
        if validator is None:
            return []
        choices = [list(present.get(pred, ())) or [None] for pred, _n, _o in params]
        out: list[Violation] = []
        for combo in itertools.product(*choices):
            bound = {name: v for (_p, name, _o), v in zip(params, combo, strict=True) if v is not None}
            out.extend(_run_validator(ctx, comp, validator, shape, focus, values, bound))
        return out

    return fn


def _make_queries(comp: Term, params: list[tuple[URIRef, str, bool]]):
    def queries(ctx, shape: Shape, present, focus: Term, values: tuple) -> list[tuple[str, dict]]:
        graph = ctx.shapes
        validator = _validator(graph, comp, shape)
        if validator is None:
            return []
        choices = [list(present.get(pred, ())) or [None] for pred, _n, _o in params]
        out: list[tuple[str, dict]] = []
        for combo in itertools.product(*choices):
            bound = {name: v for (_p, name, _o), v in zip(params, combo, strict=True) if v is not None}
            asks = list(graph.objects(validator, SH.ask))
            selects = list(graph.objects(validator, SH.select))
            if len(asks) + len(selects) != 1:
                raise ShapeError(f"{validator!r}: a validator needs exactly one sh:ask or sh:select")
            if asks:
                text = with_prefixes(ctx.plan, validator, asks[0].value)
                out.extend((text, {"this": focus, "value": value, **bound}) for value in values)
            else:
                text = substitute_path(with_prefixes(ctx.plan, validator, selects[0].value), shape)
                out.append((text, {"this": focus, **bound}))
        return out

    return queries


def _run_validator(ctx, comp: Term, validator: Term, shape: Shape, focus: Term, values: tuple, params: dict):
    graph = ctx.shapes
    messages = list(graph.objects(validator, SH.message)) or list(graph.objects(comp, SH.message))
    asks = list(graph.objects(validator, SH.ask))
    selects = list(graph.objects(validator, SH.select))
    if len(asks) + len(selects) != 1:
        raise ShapeError(f"{validator!r}: a validator needs exactly one sh:ask or sh:select")
    if asks:
        text = with_prefixes(ctx.plan, validator, asks[0].value)
        out = []
        for value in values:
            bindings = {"this": focus, "value": value, **params}
            if not run_ask(ctx, text, bindings):
                out.append(
                    Violation(value=value, messages=tuple(fill_template(m, bindings) for m in messages))
                )
        return out
    text = substitute_path(with_prefixes(ctx.plan, validator, selects[0].value), shape)
    bindings = {"this": focus, **params}
    return violations_from_solutions(
        run_select(ctx, text, bindings),
        shape=shape,
        focus=focus,
        bindings=bindings,
        messages=messages,
        graph=graph,
        annotation_source=validator,
    )


def declared_components(plan: Plan) -> list[ComponentSpec]:
    """One ComponentSpec per parameterised sh:ConstraintComponent (or subclass instance) in the plan's shapes graph.

    Components already in the registry, and non-IRI components, are skipped, so a re-declared built-in stays native. A
    component with no validator still gets a spec, whose check reports nothing. Raises ShapeError on a malformed
    parameter declaration, including one whose parameters are all optional.
    """
    graph = plan.shapes_graph
    comps: dict = {}
    for cls in _subclass_closure(graph, SH.ConstraintComponent):
        for comp in graph.subjects(RDF.type, cls):
            comps.setdefault(comp, None)
    specs: list[ComponentSpec] = []
    for comp in comps:
        if comp in REGISTRY or not isinstance(comp, URIRef):
            continue  # a built-in component re-declared in the shapes graph (e.g. the SHACL vocabulary) stays native
        params = _parameters(graph, comp)
        if not params:
            continue
        preds = tuple(p for p, _n, _o in params)
        required = tuple(p for p, _n, opt in params if not opt)
        specs.append(ComponentSpec(comp, preds, _make_fn(comp, params), required, _make_queries(comp, params)))
    return specs
