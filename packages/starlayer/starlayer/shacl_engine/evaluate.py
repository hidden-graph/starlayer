"""The SHACL 1.2 ``evaluate`` processing mode: compute the values of ``sh:values`` / ``sh:defaultValue`` on property shapes.

For every property shape with a single-predicate ``sh:path`` and every focus node it applies to (its own targets plus the
targets of each node shape that lists it with ``sh:property``), the value nodes are computed exactly as validation does
(Core, "Value Nodes of Property Shapes": the path values, plus the ``sh:values`` outputs, plus the ``sh:defaultValue``
outputs only when both are empty) and written as ``focus path value`` triples into a fresh graph. The data graph is never
modified. The result is a shape-driven subgraph, not a copy of the data graph.

Deviation from nothing in the draft but from the old function's silence: a property shape whose path is not a single
predicate (sequence, inverse, ...) is skipped, as in the old ``evaluate``, since a computed value has no triple to be
written as. A ``sh:deactivated`` given as a node expression is honoured per focus node (the old function read only the
literal); an expression that fails contributes no values.

With ``validate=True`` the evaluation is conformance-gated, the contract of ``extract_subgraph()``: the values for a focus node are
computed only when the node conforms, checked as ``validate()`` does (computed ``sh:values`` included), to the shape that targets it
(for a focus node reached through a host shape, the shape that targets the root of that chain). A node several shapes target
contributes the values of the shapes it conforms to. ``validate=False``, the default, is a lens that needs no conformance.
"""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any

from starlayer.shacl_engine import components  # noqa: F401  (registers the constraint components)
from starlayer.shacl_engine.deactivation import deactivated_at
from starlayer.shacl_engine.executor import Context, _deactivated
from starlayer.shacl_engine.plan import SH, Plan
from starlayer.shacl_engine.terms import (
    check_graphs,
    engine_view,
    to_engine,
    with_term_policy,
)


@with_term_policy
def evaluate(
    data_graph: Any,
    shapes_graph: Any = None,
    ont_graph: Any = None,
    *,
    inference: Any = None,
    focus_nodes: Iterable[Any] | None = None,
    properties: Iterable[Any] | None = None,
    rules_entailment: bool = False,
    validate: bool = False,
    plan: Plan | None = None,
) -> Any:
    """Evaluate ``sh:values`` / ``sh:defaultValue`` of ``shapes_graph`` (default: ``data_graph``) over ``data_graph``.

    ``inference`` and the shapes graph's ``sh:entailment`` regimes close the data graph first (``ont_graph`` is visible
    to that closure only); entailed triples count as stored triples. ``rules_entailment`` also runs the rules the
    shapes graph's ``sh:entailment`` selects, before evaluating. ``focus_nodes`` restricts evaluation to those nodes (the
    shapes' targets are still resolved over the whole data graph); ``properties`` to property shapes whose ``sh:path`` is one
    of those predicates. ``validate`` makes the evaluation conformance-gated (module docstring). Returns a new graph (an
    ``StarLayerGraph``) with the data graph's prefixes.
    """
    from starlayer.shacl_engine.entailment import resolve_data_view

    check_graphs((data_graph, "data graph"), (shapes_graph, "shapes graph"), (ont_graph, "ontology graph"))
    data_graph = engine_view(data_graph, "data graph")
    shapes = engine_view(shapes_graph, "shapes graph") if shapes_graph is not None else data_graph
    view = resolve_data_view(data_graph, shapes, inference=inference, ont_graph=ont_graph)
    if rules_entailment:
        from starlayer.shacl_engine.rules import apply_rules, entailment_selection

        active, sets = entailment_selection(shapes)
        if active:
            view = apply_rules(view, shapes, rule_sets=sets or None).view

    plan = plan if plan is not None else Plan(shapes_graph=shapes)
    ctx = Context(data=view, plan=plan)
    wanted_focus = None if focus_nodes is None else frozenset(to_engine(n) for n in focus_nodes)
    wanted_predicates = None if properties is None else frozenset(to_engine(p) for p in properties)

    from starlayer.shacl_engine.graphs import new_graph

    out = new_graph(data_graph)
    found: list = []

    candidates = dict.fromkeys([*plan.all_shape_nodes(), *shapes.subjects(SH.path, None)])
    for node in candidates:
        pshape = plan.shape(node)
        if pshape.path is None or pshape.path.kind != "pred" or pshape.deactivated:
            continue
        predicate = pshape.path.iri
        if wanted_predicates is not None and predicate not in wanted_predicates:
            continue
        foci = _foci(ctx, plan, shapes, node, ())
        for focus, gates in foci.items():
            if wanted_focus is not None and focus not in wanted_focus:
                continue
            if deactivated_at(ctx, pshape, focus):
                continue
            if validate and not any(ctx.conforms(gate_shape, gate_focus) for gate_shape, gate_focus in gates):
                continue
            for value in ctx.value_nodes(pshape, focus):
                found.append((focus, predicate, value))
    out.extend(found)
    return out



def _foci(ctx: Context, plan: Plan, shapes: Any, node: Any, active: tuple) -> dict[Any, dict[tuple, None]]:
    """The focus nodes a shape applies to: its own targets, plus for each shape that lists it with ``sh:property`` the
    host's focus nodes, or, when the host is itself a property shape, the host's value nodes (Core, "Value Nodes of
    Property Shapes"). Each focus node comes with its gates: the ``(shape, focus node)`` pairs it was reached from, the pairs a
    conformance-gated evaluation checks (a shape's own target is gated by the shape itself)."""
    shape = plan.shape(node)
    foci: dict[Any, dict[tuple, None]] = {f: {(node, f): None} for f in ctx.shape_focus(shape)}
    for host_node in dict.fromkeys(shapes.subjects(SH.property, node)):
        host = plan.shape(host_node)
        if host.deactivated or host_node in active or host_node == node or _deactivated(host, SH.property, node):  # also {| sh:deactivated true |} on the link
            continue
        for f, gates in _foci(ctx, plan, shapes, host_node, (*active, node)).items():
            if deactivated_at(ctx, host, f):
                continue
            if host.path is None:
                foci.setdefault(f, {}).update(gates)
            else:
                for value in ctx.value_nodes(host, f):
                    foci.setdefault(value, {}).update(gates)
    return foci
