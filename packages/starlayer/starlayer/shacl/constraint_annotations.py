"""Per-constraint ``sh:severity`` / ``sh:message`` / ``sh:deactivated`` (SHACL 1.2 Core, annotations of a constraint's triple).

``ex:S sh:class ex:Cat {| sh:severity sh:Warning ; sh:message "..." ; sh:deactivated true |}`` is an RDF 1.2 reifier ``R`` with
``R rdf:reifies <<( ex:S sh:class ex:Cat )>>``. The constraint is the triple (shape, parameter predicate, value), so a parameter
with several values has one annotation per value, and the annotation says something about that constraint only; the shape's
own ``sh:severity`` / ``sh:message`` / ``sh:deactivated`` apply to the constraints that have no annotation.

pySHACL runs every constraint through ``Shape.validate()``, which builds a component and calls its ``evaluate()``. This wraps
``evaluate()`` of each registered component class (the same single place for every component, native or pySHACL's own, and for
the user-defined SPARQL-based components) so that no component needs to know about annotations:

- no annotation on any of the component's constraint triples: the component runs unchanged (one cached lookup per triple);
- every value of the component carries the same annotation: a deactivated one is skipped, otherwise it runs once and its
  results get the annotation's severity and messages;
- the values carry different annotations: each distinct annotation runs on its own, the component rebuilt with the other
  values hidden from the shapes graph for the duration of that run, so each result is attributed to the constraint that
  produced it (not possible to do after the fact, a result does not say which value it came from).

``sh:qualifiedValueShape`` is one component with two result kinds, so its results are attributed by result component: the
min-count results use the ``sh:qualifiedMinCount`` annotation (else the value shape's), the max-count ones the
``sh:qualifiedMaxCount`` one. ``sh:property`` keeps its own handling in ``native_components`` (only ``sh:deactivated`` means
something there: the results belong to the property shape, which has its own severity and messages).
"""

from __future__ import annotations

import contextlib
import functools
import re
from typing import Any

from rdflib import Literal, Namespace, URIRef

SH = Namespace("http://www.w3.org/ns/shacl#")
_RDF_REIFIES = URIRef("http://www.w3.org/1999/02/22-rdf-syntax-ns#reifies")

_SENTINEL = "_starlayer_shacl_constraint_annotation_patch"
_STATE_ATTR = "_starlayer_constraint_annotation_state"
_ACTIVE_ATTR = "_starlayer_constraint_annotation_active"

# Parameters that qualify another constraint and are not a constraint of their own.
_COMPANION_PARAMETERS = frozenset({SH.qualifiedValueShapesDisjoint, SH.ignoredProperties})

_NO_ANNOTATION: tuple[Any, ...] = (None, None, ())


def _state(sg: Any) -> dict[str, Any] | None:
    """Per-``ShapesGraph`` cache (the graph is rebuilt for each validation, so it never outlives one)."""
    store = getattr(sg, "__dict__", None)
    if store is None:
        return None
    state = store.get(_STATE_ATTR)
    if state is None:
        has_reifiers = next(iter(sg.graph.triples((None, _RDF_REIFIES, None))), None) is not None
        state = store[_STATE_ATTR] = {"has_reifiers": has_reifiers, "units": {}}
    return state


def _unit_annotation(sg: Any, state: dict[str, Any], node: Any, predicate: Any, value: Any) -> tuple[Any, ...]:
    """``(deactivated, severity, messages)`` of the constraint triple, ``_NO_ANNOTATION`` if it has no reifier.

    ``deactivated`` is a bool when the annotation gives exactly one ``sh:deactivated`` value, else ``None``; ``severity`` is
    the single ``sh:severity`` value or ``None``; ``messages`` is every ``sh:message`` value, sorted.
    """
    from starlayer.shacl.native_components import _get_tt_adapter

    key = (node, predicate, value)
    cached = state["units"].get(key)
    if cached is not None:
        return cached
    graph = sg.graph
    adapter = _get_tt_adapter(graph)
    term = adapter.encode_term((node, predicate, value)) if adapter is not None else (node, predicate, value)
    deactivated: set[Any] = set()
    severities: set[Any] = set()
    messages: set[Any] = set()
    for reifier, _, _ in graph.triples((None, _RDF_REIFIES, term)):
        deactivated.update(graph.objects(reifier, SH.deactivated))
        severities.update(graph.objects(reifier, SH.severity))
        messages.update(graph.objects(reifier, SH.message))
    result: tuple[Any, ...] = (
        (next(iter(deactivated)) == Literal(True)) if len(deactivated) == 1 else None,
        next(iter(severities)) if len(severities) == 1 else None,
        tuple(sorted(messages, key=lambda m: (str(m), getattr(m, "language", None) or ""))),
    )
    if result[0] is None and result[1] is None and not result[2]:
        result = _NO_ANNOTATION
    state["units"][key] = result
    return result


def _effective(annotation: tuple[Any, ...]) -> tuple[Any, ...]:
    """The annotation as it changes behaviour: ``sh:deactivated false`` is the same as no annotation."""
    return (annotation[0] is True, annotation[1], annotation[2])


_PLAIN = (False, None, ())


def _component_units(component: Any) -> list[tuple[Any, Any]]:
    """The constraint triples ``(predicate, value)`` of a built component, on its shape."""
    shape = component.shape
    sg = shape.sg
    constraint = getattr(component, "constraint", None)  # a user-defined SPARQL-based component
    if constraint is not None and hasattr(constraint, "parameters"):
        predicates = []
        for parameter in constraint.parameters:
            try:
                predicates.append(parameter.path())
            except Exception:  # pragma: no cover - a parameter without a usable path has no constraint triple
                continue
    else:
        predicates = [p for p in type(component).constraint_parameters() if p not in _COMPANION_PARAMETERS]
    return [(p, v) for p in predicates for v in sg.objects(shape.node, p)]


def _restyle(report: Any, sg: Any, severity: Any, messages: tuple[Any, ...]) -> Any:
    """One ``(description, result node, triples)`` report with the annotation's severity and messages."""
    desc, r_node, r_triples = report
    if severity is None and not messages:
        return report
    new_triples = []
    for t in r_triples:
        s, p, o = t
        if s == r_node and severity is not None and p == SH.resultSeverity:
            continue
        if s == r_node and messages and p == SH.resultMessage:
            continue
        new_triples.append(t)
    if severity is not None:
        new_triples.append((r_node, SH.resultSeverity, severity))
    new_triples.extend((r_node, SH.resultMessage, m) for m in messages)
    if isinstance(desc, str):
        try:
            from pyshacl.rdfutil import stringify_node

            if severity is not None:
                text = stringify_node(sg.graph, severity)
                desc = re.sub(r"(?m)^\tSeverity: .*$", lambda _m: f"\tSeverity: {text}", desc, count=1)
                head = "Constraint Violation" if severity == SH.Violation else "Validation Result"
                desc = re.sub(r"^(Constraint Violation|Validation Result)", head, desc, count=1)
        except Exception:  # pragma: no cover - the text is a convenience, the graph is the report
            pass
        if messages:
            desc = "".join(line for line in desc.splitlines(keepends=True) if not line.startswith("\tMessage: "))
            if desc and not desc.endswith("\n"):
                desc += "\n"
            desc += "".join(f"\tMessage: {getattr(m, 'value', m)}\n" for m in messages)
    return desc, r_node, new_triples


@contextlib.contextmanager
def _hidden(graph: Any, node: Any, units: list[tuple[Any, Any]]):
    removed = []
    for p, v in units:
        if (node, p, v) in graph:
            graph.remove((node, p, v))
            removed.append((node, p, v))
    try:
        yield
    finally:
        for triple in removed:
            graph.add(triple)


def _result_component(r_triples: Any, r_node: Any) -> Any:
    for s, p, o in r_triples:
        if s == r_node and p == SH.sourceConstraintComponent:
            return o if not isinstance(o, tuple) else o[1]
    return None


def _evaluate_qualified(self: Any, original: Any, state: dict[str, Any], args: tuple[Any, ...]) -> Any:
    """``sh:qualifiedValueShape`` and its counts: attribute each result by its component (min or max)."""
    shape = self.shape
    sg = shape.sg
    node = shape.node

    def annotation(count_predicate: Any) -> tuple[Any, ...]:
        counts = [_unit_annotation(sg, state, node, count_predicate, v) for v in sg.objects(node, count_predicate)]
        shapes = {_unit_annotation(sg, state, node, SH.qualifiedValueShape, v) for v in sg.objects(node, SH.qualifiedValueShape)}
        own = counts[0] if len(counts) == 1 else _NO_ANNOTATION
        inherited = next(iter(shapes)) if len(shapes) == 1 else _NO_ANNOTATION
        return tuple(a if a not in (None, ()) else b for a, b in zip(own, inherited, strict=True))

    by_component = {
        SH.QualifiedMinCountConstraintComponent: _effective(annotation(SH.qualifiedMinCount)),
        SH.QualifiedMaxCountConstraintComponent: _effective(annotation(SH.qualifiedMaxCount)),
    }
    if all(a == _PLAIN for a in by_component.values()):
        return original(self, *args)
    _, reports = original(self, *args)
    kept = []
    for report in reports:
        deactivated, severity, messages = by_component.get(_result_component(report[2], report[1]), _PLAIN)
        if deactivated:
            continue
        kept.append(_restyle(report, sg, severity, messages))
    return not kept, kept


def _wrap(original: Any) -> Any:
    @functools.wraps(original)
    def evaluate(self: Any, *args: Any, **kwargs: Any) -> Any:
        if kwargs or self.__dict__.get(_ACTIVE_ATTR):
            return original(self, *args, **kwargs)
        sg = getattr(getattr(self, "shape", None), "sg", None)
        state = _state(sg) if sg is not None and hasattr(sg, "graph") else None
        if not state or not state["has_reifiers"]:
            return original(self, *args)
        self.__dict__[_ACTIVE_ATTR] = True
        try:
            return _evaluate_annotated(self, original, sg, state, args)
        finally:
            self.__dict__.pop(_ACTIVE_ATTR, None)

    setattr(evaluate, _SENTINEL, True)
    return evaluate


def _evaluate_annotated(self: Any, original: Any, sg: Any, state: dict[str, Any], args: tuple[Any, ...]) -> Any:
    from starlayer.shacl.component_cache import uncached

    shape = self.shape
    if getattr(type(self), "constraint_parameters", None) is not None and SH.qualifiedValueShape in type(self).constraint_parameters():
        return _evaluate_qualified(self, original, state, args)
    units = _component_units(self)
    annotations = {u: _effective(_unit_annotation(sg, state, shape.node, u[0], u[1])) for u in units}
    groups: dict[tuple[Any, ...], list[tuple[Any, Any]]] = {}
    for unit, effective in annotations.items():
        groups.setdefault(effective, []).append(unit)
    if not groups or set(groups) == {_PLAIN}:
        return original(self, *args)
    if len(groups) == 1:
        (deactivated, severity, messages), = groups
        if deactivated:
            return True, []
        conforms, reports = original(self, *args)
        return conforms, [_restyle(r, sg, severity, messages) for r in reports]
    if getattr(self, "constraint", None) is not None:
        return original(self, *args)  # a user-defined component whose parameter values differ in annotation: not split
    conforms = True
    out: list[Any] = []
    for (deactivated, severity, messages), members in groups.items():
        if deactivated:
            continue
        hidden = [u for u in units if u not in members]
        with _hidden(sg.graph, shape.node, hidden), uncached():
            part = type(self)(shape)
            part_conforms, part_reports = original(part, *args)
        conforms = conforms and part_conforms
        out.extend(_restyle(r, sg, severity, messages) for r in part_reports)
    return conforms, out


def install_constraint_annotation_patch() -> bool:
    """Wrap ``evaluate`` of every registered constraint component class. True if installed or already installed.

    Process-global and idempotent, like the other pySHACL patches; a component registered since the last call is wrapped too.
    """
    try:
        from pyshacl.constraints import CONSTRAINT_PARAMETERS_MAP
        from pyshacl.constraints.constraint_component import ConstraintComponent
    except Exception:  # pragma: no cover - pyshacl missing or restructured: run unpatched
        return False
    classes = set(CONSTRAINT_PARAMETERS_MAP.values())
    for module, name in (
        ("pyshacl.constraints.advanced", "ExpressionConstraint"),
        ("pyshacl.constraints.sparql.sparql_based_constraint_components", "BoundShapeValidatorComponent"),
    ):
        try:
            classes.add(getattr(__import__(module, fromlist=[name]), name))
        except Exception:  # pragma: no cover
            continue
    for component_cls in classes:
        if not (isinstance(component_cls, type) and issubclass(component_cls, ConstraintComponent)):
            continue
        if component_cls.__name__.startswith("PropertyConstraintComponent"):
            continue  # sh:property: see the module docstring
        evaluate = component_cls.evaluate
        if getattr(evaluate, _SENTINEL, False):
            continue
        component_cls.evaluate = _wrap(evaluate)
    return True
