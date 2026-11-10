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

A component with one parameter (``sh:class``, a user-defined component with a single ``sh:parameter``) has one constraint per
value; a component with several parameters is one constraint whose parameter triples may all carry the annotation:
``sh:pattern`` with ``sh:flags``, ``sh:closed`` with ``sh:ignoredProperties``, ``sh:reifierShape`` with
``sh:reificationRequired``, a user-defined component with several parameters. The annotations of the triples of one constraint
are merged: any ``sh:deactivated`` that says true deactivates it, messages are united, and two different severities (ill-formed:
at most one is allowed) resolve to the most severe (Violation, Warning, Info, Debug, Trace; any other IRI after them, by IRI), a
triple's own value taking precedence over a companion triple's. The value of ``sh:deactivated`` is a node expression: a literal
is the constant, a ``shnex:``/``sparql:`` expression (stripped from the shapes graph by the validator, which keeps the reifier ->
expression map in ``_deactivated_expr_registry``) is evaluated once per focus node, as a shape's is, and only an output of
exactly true deactivates (an expression that cannot be evaluated leaves the constraint active).

``sh:qualifiedValueShape`` is one component with two result kinds, so its results are attributed by result component: the
min-count results use the ``sh:qualifiedMinCount`` annotation (else the value shape's, else the disjoint flag's), the max-count
ones the ``sh:qualifiedMaxCount`` one. ``sh:property`` keeps its own handling in ``native_components`` (only ``sh:deactivated`` means
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

# Parameters that qualify another parameter of the same constraint and are not a constraint of their own.
_COMPANION_PARAMETERS = frozenset(
    {SH.qualifiedValueShapesDisjoint, SH.ignoredProperties, SH.flags, SH.reificationRequired}
)

_SEVERITY_ORDER = {SH.Violation: 0, SH.Warning: 1, SH.Info: 2, SH.Debug: 3, SH.Trace: 4}

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


def _most_severe(severities: Any) -> Any:
    """The one severity of an ill-formed set (two reifiers disagree): the most severe, then by IRI, so it is deterministic."""
    return min(severities, key=lambda v: (_SEVERITY_ORDER.get(v, len(_SEVERITY_ORDER)), str(v))) if severities else None


def _unit_annotation(sg: Any, state: dict[str, Any], node: Any, predicate: Any, value: Any) -> tuple[Any, ...]:
    """``(deactivated, severity, messages)`` of the constraint triple, ``_NO_ANNOTATION`` if it has no reifier.

    ``deactivated`` is ``True`` (a literal true), a sorted tuple of node-expression nodes (decided per focus node), or ``None``;
    ``severity`` is the most severe ``sh:severity`` value or ``None``; ``messages`` is every ``sh:message`` value, sorted.
    """
    from starlayer.shacl.native_components import _get_tt_adapter
    from starlayer.shacl.validator import _deactivated_expr_registry

    key = (node, predicate, value)
    cached = state["units"].get(key)
    if cached is not None:
        return cached
    graph = sg.graph
    adapter = _get_tt_adapter(graph)
    term = adapter.encode_term((node, predicate, value)) if adapter is not None else (node, predicate, value)
    registry = _deactivated_expr_registry.get() or {}
    constant = False
    expressions: set[Any] = set()
    severities: set[Any] = set()
    messages: set[Any] = set()
    for reifier, _, _ in graph.triples((None, _RDF_REIFIES, term)):
        values = set(graph.objects(reifier, SH.deactivated))
        if reifier in registry:
            values.add(registry[reifier])
        for v in values:
            if isinstance(v, Literal):
                constant = constant or v == Literal(True)
            else:
                expressions.add(v)
        severities.update(graph.objects(reifier, SH.severity))
        messages.update(graph.objects(reifier, SH.message))
    deactivated = True if constant else (tuple(sorted(expressions, key=str)) or None)
    result: tuple[Any, ...] = (
        deactivated,
        _most_severe(severities),
        tuple(sorted(messages, key=lambda m: (str(m), getattr(m, "language", None) or ""))),
    )
    if result[0] is None and result[1] is None and not result[2]:
        result = _NO_ANNOTATION
    state["units"][key] = result
    return result


def _merge(*levels: list[tuple[Any, ...]]) -> tuple[Any, ...]:
    """The annotation of one constraint from the annotations of its parameter triples, most specific level first.

    Deactivation is the union over every level (true if any is, else the expressions of all of them); severity and messages come
    from the first level that has any (the most severe severity of that level, all its messages).
    """
    flat = [a for level in levels for a in level if a != _NO_ANNOTATION]
    if not flat:
        return _NO_ANNOTATION
    if any(a[0] is True for a in flat):
        deactivated: Any = True
    else:
        exprs = {e for a in flat if isinstance(a[0], tuple) for e in a[0]}
        deactivated = tuple(sorted(exprs, key=str)) or None
    severity = None
    messages: tuple[Any, ...] = ()
    for level in levels:
        severity = severity if severity is not None else _most_severe({a[1] for a in level if a[1] is not None})
        if not messages:
            messages = tuple(sorted({m for a in level for m in a[2]}, key=lambda m: (str(m), getattr(m, "language", None) or "")))
    return (deactivated, severity, messages)


def _effective(annotation: tuple[Any, ...]) -> tuple[Any, ...]:
    """The annotation as it changes behaviour: no ``sh:deactivated`` and ``sh:deactivated false`` are the same."""
    d = annotation[0]
    return (d if (d is True or isinstance(d, tuple)) else False, annotation[1], annotation[2])


_PLAIN = (False, None, ())


def _is_deactivated(deactivated: Any, focus: Any, data_graph: Any, sg: Any) -> bool:
    """True for a constant true, or when any of the expressions gives true as its only output for the focus node."""
    if deactivated is True:
        return True
    if not deactivated:
        return False
    from starlayer.shacl.node_expressions import eval_expr

    for expr in deactivated:
        try:
            computed = eval_expr(expr, focus, data_graph, sg)
        except Exception:
            continue  # cannot be evaluated: active, as for a shape
        if len(computed) == 1 and next(iter(computed)) in (Literal(True), True):
            return True
    return False


def _active_args(args: tuple[Any, ...], deactivated: Any, sg: Any) -> tuple[Any, ...] | None:
    """``args`` of ``evaluate`` without the focus nodes the annotation deactivates; ``None`` if there is none left."""
    if not isinstance(deactivated, tuple):
        return None if deactivated is True else args
    focus_value_nodes = {
        f: v for f, v in args[2].items() if not _is_deactivated(deactivated, f, args[1], sg)
    }
    if not focus_value_nodes:
        return None
    return (*args[:2], focus_value_nodes, *args[3:])


def _parameters(component: Any) -> tuple[list[Any], list[Any]]:
    """``(primary, companion)`` parameter predicates of a built component."""
    constraint = getattr(component, "constraint", None)  # a user-defined SPARQL-based component
    if constraint is not None and hasattr(constraint, "parameters"):
        predicates = []
        for parameter in constraint.parameters:
            try:
                predicates.append(parameter.path())
            except Exception:  # pragma: no cover - a parameter without a usable path has no constraint triple
                continue
        return predicates, []
    predicates = list(type(component).constraint_parameters())
    if SH.pattern in predicates and SH.flags not in predicates:
        predicates.append(SH.flags)
    return [p for p in predicates if p not in _COMPANION_PARAMETERS], [p for p in predicates if p in _COMPANION_PARAMETERS]


def _component_constraints(component: Any, sg: Any, state: dict[str, Any]) -> list[tuple[list[tuple[Any, Any]], tuple[Any, ...]]]:
    """``[(primary units, annotation)]``: one entry per constraint of the component on its shape.

    One primary parameter: a constraint per value, the companion parameters' triples (``sh:flags``, ``sh:ignoredProperties``)
    shared by all of them. Several primary parameters (a user-defined component): one constraint with every triple.
    """
    node = component.shape.node
    primary, companion = _parameters(component)
    companion_anns = [_unit_annotation(sg, state, node, p, v) for p in companion for v in sg.objects(node, p)]
    if len(primary) == 1:
        return [
            ([(primary[0], v)], _merge([_unit_annotation(sg, state, node, primary[0], v)], companion_anns))
            for v in sg.objects(node, primary[0])
        ]
    units = [(p, v) for p in primary for v in sg.objects(node, p)]
    if not units:
        return []
    return [(units, _merge([_unit_annotation(sg, state, node, p, v) for p, v in units], companion_anns))]


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


def _report_focus(r_triples: Any, r_node: Any) -> Any:
    for s, p, o in r_triples:
        if s == r_node and p == SH.focusNode:
            return o if not isinstance(o, tuple) else o[1]
    return None


def _evaluate_qualified(self: Any, original: Any, state: dict[str, Any], args: tuple[Any, ...]) -> Any:
    """``sh:qualifiedValueShape`` and its counts: attribute each result by its component (min or max).

    The constraint of a count component is its own count triple, with the value shape's and the disjoint flag's triples as the
    shared ones (a count's own annotation wins over them).
    """
    shape = self.shape
    sg = shape.sg
    node = shape.node

    def annotation(count_predicate: Any) -> tuple[Any, ...]:
        own = [_unit_annotation(sg, state, node, count_predicate, v) for v in sg.objects(node, count_predicate)]
        shared = [
            _unit_annotation(sg, state, node, p, v)
            for p in (SH.qualifiedValueShape, SH.qualifiedValueShapesDisjoint)
            for v in sg.objects(node, p)
        ]
        return _effective(_merge(own, shared))

    by_component = {
        SH.QualifiedMinCountConstraintComponent: annotation(SH.qualifiedMinCount),
        SH.QualifiedMaxCountConstraintComponent: annotation(SH.qualifiedMaxCount),
    }
    if all(a == _PLAIN for a in by_component.values()):
        return original(self, *args)
    _, reports = original(self, *args)
    kept = []
    for report in reports:
        deactivated, severity, messages = by_component.get(_result_component(report[2], report[1]), _PLAIN)
        if deactivated and _is_deactivated(deactivated, _report_focus(report[2], report[1]), args[1], sg):
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
    constraints = [(units, _effective(annotation)) for units, annotation in _component_constraints(self, sg, state)]
    groups: dict[tuple[Any, ...], list[tuple[Any, Any]]] = {}
    for units, effective in constraints:
        groups.setdefault(effective, []).extend(units)
    if not groups or set(groups) == {_PLAIN}:
        return original(self, *args)
    if len(groups) == 1:
        ((deactivated, severity, messages),) = groups
        run_args = _active_args(args, deactivated, sg)
        if run_args is None:
            return True, []
        conforms, reports = original(self, *run_args)
        return conforms, [_restyle(r, sg, severity, messages) for r in reports]
    # Constraints that differ in annotation: each runs alone, the other values of the parameter hidden. pySHACL binds one value
    # of a user-defined component's parameter whatever it has, so there each constraint (value) is run on its own.
    user_defined = getattr(self, "constraint", None) is not None
    all_units = [u for units, _ in constraints for u in units]
    runs = (
        [(units, effective) for units, effective in constraints]
        if user_defined
        else [(members, effective) for effective, members in groups.items()]
    )
    conforms = True
    out: list[Any] = []
    for members, (deactivated, severity, messages) in runs:
        run_args = _active_args(args, deactivated, sg)
        if run_args is None:
            continue
        hidden = [u for u in all_units if u not in members]
        with _hidden(sg.graph, shape.node, hidden), uncached():
            if user_defined:
                part = type(self)(self.constraint, shape, self.validator)
            else:
                part = type(self)(shape)
            part_conforms, part_reports = original(part, *run_args)
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
