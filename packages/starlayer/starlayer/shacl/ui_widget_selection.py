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
    focus_node: Any | None,
    data_graph: Any | None,
    shapes_graph: Any,
    scoring_graph: Any,
) -> bool:
    """Section 3.4 Matcher Function, step for step:

    1. No focus node, a ``shui:dataGraphShape`` present and no
       ``shui:shapesGraphShape``: reject - the only condition cannot be checked.
    2. The shape node is validated in the *shapes graph* against the
       matcher's ``shui:shapesGraphShape``, whose definition is read from the
       *scoring graph*. Reject on failure.
    3. No focus node: accept.
    4. The focus node is validated in the *data graph* against the
       matcher's ``shui:dataGraphShape``. The spec reads that shape from the
       shapes graph; the scoring graph is searched too, so a catalog that
       defines it alongside the matcher also works.
    """
    shapes_graph_shape = next(scoring_graph.objects(matcher, SHUI.shapesGraphShape), None)
    data_graph_shape = next(scoring_graph.objects(matcher, SHUI.dataGraphShape), None)

    if focus_node is None and data_graph_shape is not None and shapes_graph_shape is None:
        return False

    if shapes_graph_shape is not None and not _node_conforms(
        shape_node, shapes_graph_shape, base_graph=shapes_graph, shapes_graph=scoring_graph
    ):
        return False

    if focus_node is None:
        return True

    if data_graph_shape is not None:
        from starlayer.graph.graph.starlayer_graph import StarLayerGraph

        shape_definitions = StarLayerGraph()
        shape_definitions += shapes_graph
        shape_definitions += scoring_graph
        if not _node_conforms(
            focus_node, data_graph_shape, base_graph=data_graph, shapes_graph=shape_definitions
        ):
            return False

    return True


def select_widget(
    *,
    shape_node: Any,
    focus_node: Any | None = None,
    data_graph: Any | None = None,
    shapes_graph: Any,
    scoring_graph: Any | None = None,
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

    ``focus_node`` and ``data_graph`` are optional. They are used only to
    check a matcher's ``shui:dataGraphShape``. With no ``focus_node`` a matcher
    that has only a data condition rejects its widget (Section 3.4 step 1),
    while one with a ``shui:shapesGraphShape`` is decided by that alone, so
    the choice is per shape rather than per node. Passing a ``focus_node``
    without a ``data_graph`` raises ``ValueError``.

    ``scoring_graph`` is optional: omit it (or pass ``None``) when widgets
    are fixed in the shapes graph and there is no scoring catalog - an
    explicit ``shui:editor``/``shui:viewer`` is then accepted outright, and a
    property with none gets ``None``.
    """
    if focus_node is not None and data_graph is None:
        raise ValueError("focus_node needs a data_graph to check its shui:dataGraphShape against")
    if scoring_graph is None:
        from starlayer.graph.graph.starlayer_graph import StarLayerGraph

        scoring_graph = StarLayerGraph()
    predicate = SHUI.editor if role == "editor" else SHUI.viewer
    explicit_widget = next(shapes_graph.objects(shape_node, predicate), None)
    if explicit_widget is not None:
        matcher = _find_matcher(explicit_widget, scoring_graph)
        if matcher is None or _matcher_accepts(
            matcher,
            shape_node=shape_node,
            focus_node=focus_node,
            data_graph=data_graph,
            shapes_graph=shapes_graph,
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
    # highest score first, then by widget IRI codepoints (Section 3.5 step 2)
    ranked.sort(key=lambda pair: (-pair[0], str(pair[1])))

    for _score, widget in ranked:
        matcher = _find_matcher(widget, scoring_graph)
        if matcher is None or _matcher_accepts(
            matcher,
            shape_node=shape_node,
            focus_node=focus_node,
            data_graph=data_graph,
            shapes_graph=shapes_graph,
            scoring_graph=scoring_graph,
        ):
            return widget

    return None


def select_widgets(
    *,
    shape_node: Any,
    focus_node: Any | None = None,
    data_graph: Any | None = None,
    shapes_graph: Any,
    scoring_graph: Any | None = None,
    role: Role,
) -> dict[Any, URIRef | None]:
    """Batch sibling of :func:`select_widget` - walks ``shape_node``'s own
    ``sh:property`` list and runs :func:`select_widget` once per property,
    returning ``{property_shape: widget}`` for the given ``role``
    (``"editor"`` or ``"viewer"``). Every ``sh:property`` of ``shape_node``
    is a key.

    ``shape_node`` is a ``sh:NodeShape`` here (unlike :func:`select_widget`,
    whose own ``shape_node`` is a single property shape) - its
    ``sh:property`` list is exactly what's walked.

    A property for which :func:`select_widget` returns ``None`` maps to
    ``None``, so the dict always lists every property of the shape.

    ``focus_node``, ``data_graph`` and ``scoring_graph`` are optional, as
    for :func:`select_widget`.
    """
    result: dict[Any, URIRef | None] = {}
    for prop in shapes_graph.objects(shape_node, SH.property):
        widget = select_widget(
            shape_node=prop, focus_node=focus_node,
            data_graph=data_graph, shapes_graph=shapes_graph, scoring_graph=scoring_graph, role=role,
        )
        result[prop] = widget
    return result
