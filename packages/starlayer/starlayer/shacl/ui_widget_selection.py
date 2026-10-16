"""SHACL 1.2 User Interfaces' widget *selection* algorithm
(``shui:WidgetScore``/``shui:WidgetAcceptMatcher``,
https://www.w3.org/TR/shacl12-ui/ Section 3 "Scoring System") - not a
pySHACL patch, new additive public surface built entirely on the existing
public ``starlayer.shacl.validate()``. The spec's own Matcher Function is
"two ordinary SHACL validations" (the shape node against a scoring-graph
shape, the focus node against a data-graph shape), confirmed via a direct
spec fetch - see ``docs/shacl/implementation-plan.md`` item 3 for the full
design history this module executes.

``shui:editor``/``shui:viewer`` annotations (compatibility, not selection)
are a separate, already-shipped concern - see
``starlayer.starontology``'s ``stsh:ShuiPredicateShapes`` and
``docs/guides/04d-shacl-ui.ipynb``.

**Deliberately tolerant of `shui:WidgetAcceptMatcher`'s own cardinality**:
as of the 2026-10-16 spec re-check, `shui:WidgetAcceptMatcher` has no
formal upstream shape at all (unlike `shui:WidgetScore`, which does - see
`starontology`'s own `stsh:WidgetScoreShape`), and is actively contested
upstream (w3c/data-shapes#1249, open/unmerged, proposing to change its
`shui:widget` cardinality from "exactly one" to "at least one"). This
module reads whatever `shui:widget`/`shui:dataGraphShape`/
`shui:shapesGraphShape` triples are actually present on a matcher node
directly, assuming no particular cardinality, so it tolerates either
reading without needing to change if/when that PR lands.
"""

from __future__ import annotations

from typing import Any, Literal

from rdflib import RDF, BNode, Namespace, URIRef

from starlayer.shacl.validator import validate

SHUI = Namespace("http://www.w3.org/ns/shacl-ui#")
SH = Namespace("http://www.w3.org/ns/shacl#")

Role = Literal["editor", "viewer"]


def _node_conforms(node: Any, shape: Any, *, base_graph: Any, shapes_graph: Any) -> bool:
    """True iff ``node`` (a resource in ``base_graph``) conforms to
    ``shape`` (a shape already defined somewhere in ``shapes_graph``) -
    built by wrapping ``shape`` in a throwaway ``sh:targetNode``/``sh:node``
    probe shape, rather than a private helper, so this stays on
    ``starlayer.shacl``'s own public surface only.
    """
    from starlayer.graph.graph.starlayer_graph import StarLayerGraph

    probe_shapes = StarLayerGraph()
    probe_shapes += shapes_graph
    wrapper = BNode()
    probe_shapes.add((wrapper, RDF.type, SH.NodeShape))
    probe_shapes.add((wrapper, SH.targetNode, node))
    probe_shapes.add((wrapper, SH.node, shape))
    result = validate(base_graph, probe_shapes, meta_shacl=False)
    return result.conforms


def _find_matcher(widget: Any, scoring_graph: Any) -> Any | None:
    """The ``shui:WidgetAcceptMatcher`` naming ``widget`` via its own
    ``shui:widget`` value(s), or ``None`` if ``widget`` has none - no
    cardinality assumed on either side (see module docstring)."""
    for matcher in scoring_graph.subjects(SHUI.widget, widget):
        if (matcher, RDF.type, SHUI.WidgetAcceptMatcher) in scoring_graph:
            return matcher
    return None


def _matcher_accepts(
    matcher: Any,
    *,
    shape_node: Any,
    focus_node: Any,
    data_graph: Any,
    scoring_graph: Any,
) -> bool:
    """Section 3.4 Matcher Function: the shape node against the matcher's
    own ``shui:shapesGraphShape`` (checked within ``scoring_graph``, where
    both the matcher and that shape's definition live) and the focus node
    against its ``shui:dataGraphShape`` (checked within ``data_graph``) -
    either absent counts as unconstrained on that axis, matching ordinary
    SHACL "no constraint means no restriction" semantics."""
    shapes_graph_shape = next(scoring_graph.objects(matcher, SHUI.shapesGraphShape), None)
    if shapes_graph_shape is not None and not _node_conforms(
        shape_node, shapes_graph_shape, base_graph=scoring_graph, shapes_graph=scoring_graph
    ):
        return False

    data_graph_shape = next(scoring_graph.objects(matcher, SHUI.dataGraphShape), None)
    if data_graph_shape is not None and not _node_conforms(
        focus_node, data_graph_shape, base_graph=data_graph, shapes_graph=scoring_graph
    ):
        return False

    return True


def select_widget(
    shape_node: Any,
    focus_node: Any,
    *,
    data_graph: Any,
    shapes_graph: Any,
    scoring_graph: Any,
    role: Role,
) -> URIRef | None:
    """Select the ``shui:editor``/``shui:viewer`` widget ``shape_node``
    should use for ``focus_node``, per the spec's own Section 3.2 "Select
    Function" procedure:

    1. If ``shape_node`` already has an explicit ``shui:editor``/
       ``shui:viewer`` (per ``role``), look up its ``shui:WidgetAcceptMatcher``
       - no matcher found means accept unconditionally; a matcher that
       accepts also means accept; a matcher that rejects falls through to
       step 2 rather than failing outright.
    2. Otherwise (or on fallthrough), collect every ``shui:WidgetScore`` in
       ``scoring_graph`` with both a ``shui:widget`` and a ``shui:score``,
       ranked highest-score-first.
    3. Walk that ranked list, running the same matcher check on each,
       returning the first one that's either unmatched or accepted.

    Returns ``None`` if nothing matches at all. ``data_graph``/
    ``shapes_graph``/``scoring_graph`` may be the same object - the spec
    doesn't require them to be separate graphs, just separate *roles*.
    """
    predicate = SHUI.editor if role == "editor" else SHUI.viewer
    explicit_widget = next(shapes_graph.objects(shape_node, predicate), None)
    if explicit_widget is not None:
        matcher = _find_matcher(explicit_widget, scoring_graph)
        if matcher is None or _matcher_accepts(
            matcher,
            shape_node=shape_node,
            focus_node=focus_node,
            data_graph=data_graph,
            scoring_graph=scoring_graph,
        ):
            return explicit_widget

    ranked: list[tuple[float, Any]] = []
    for score_node in scoring_graph.subjects(RDF.type, SHUI.WidgetScore):
        widget = next(scoring_graph.objects(score_node, SHUI.widget), None)
        score_value = next(scoring_graph.objects(score_node, SHUI.score), None)
        if widget is None or score_value is None:
            continue
        ranked.append((float(score_value), widget))
    ranked.sort(key=lambda pair: pair[0], reverse=True)

    for _score, widget in ranked:
        matcher = _find_matcher(widget, scoring_graph)
        if matcher is None or _matcher_accepts(
            matcher,
            shape_node=shape_node,
            focus_node=focus_node,
            data_graph=data_graph,
            scoring_graph=scoring_graph,
        ):
            return widget

    return None


def select_widgets(
    shape_node: Any,
    focus_node: Any,
    *,
    data_graph: Any,
    shapes_graph: Any,
    scoring_graph: Any,
    role: Role,
) -> Any:
    """Batch sibling of :func:`select_widget` - walks ``shape_node``'s own
    ``sh:property`` list and runs :func:`select_widget` once per property,
    assembling the results into one graph of ``(property_shape,
    shui:editor|shui:viewer, widget)`` triples, rather than one value per
    call. Mirrors this package's own ``evaluate()`` precedent (compute
    something per property shape, return the result as one assembled
    graph) instead of inventing a new shape.

    ``shape_node`` is a ``sh:NodeShape`` here (unlike :func:`select_widget`,
    whose own ``shape_node`` is a single property shape) - its
    ``sh:property`` list is exactly what's walked.

    A property for which :func:`select_widget` returns ``None`` contributes
    no triple at all - absence, not an asserted null.
    """
    from starlayer.graph.graph.starlayer_graph import StarLayerGraph

    predicate = SHUI.editor if role == "editor" else SHUI.viewer
    result = StarLayerGraph()
    for prop in shapes_graph.objects(shape_node, SH.property):
        widget = select_widget(
            prop, focus_node,
            data_graph=data_graph, shapes_graph=shapes_graph, scoring_graph=scoring_graph, role=role,
        )
        if widget is not None:
            result.add((prop, predicate, widget))
    return result
