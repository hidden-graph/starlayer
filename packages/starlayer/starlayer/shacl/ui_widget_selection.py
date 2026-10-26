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

from dataclasses import dataclass, field
from typing import Any, Literal

from rdflib import RDF, BNode, Namespace, URIRef

from starlayer.shacl.validator import validate

SHUI = Namespace("http://www.w3.org/ns/shacl-ui#")
SH = Namespace("http://www.w3.org/ns/shacl#")

Role = Literal["editor", "viewer"]

# The built-in widgets of SHACL 1.2 UI, Section 9.1 (editors) and 9.2 (viewers). The draft does not publish the
# vocabulary in machine-readable form, so the lists are kept here; a test compares them with the 26 widgets the
# shipped shapes graph documents.
_BUILTIN_EDITORS = frozenset(
    SHUI[name]
    for name in (
        "AutoCompleteEditor", "BlankNodeEditor", "BooleanEditor", "DatePickerEditor", "DateTimePickerEditor",
        "DetailsEditor", "EnumSelectEditor", "InstancesSelectEditor", "IRIEditor", "NumberFieldEditor",
        "RichTextEditor", "SubClassEditor", "TextAreaEditor", "TextAreaWithLangEditor", "TextFieldEditor",
        "TextFieldWithLangEditor",
    )
)
_BUILTIN_VIEWERS = frozenset(
    SHUI[name]
    for name in (
        "BlankNodeViewer", "DetailsViewer", "HTMLViewer", "HyperlinkViewer", "ImageViewer", "IRIViewer",
        "LabelViewer", "LangStringViewer", "LiteralViewer", "ValueTableViewer",
    )
)
_EDITOR_CLASSES = (SHUI.Editor, SHUI.SingleEditor, SHUI.MultiEditor)
_VIEWER_CLASSES = (SHUI.Viewer, SHUI.SingleViewer, SHUI.MultiViewer)


def _widget_roles(widget: Any, *graphs: Any) -> set[str]:
    """The roles ``widget`` is known to have: ``"editor"``, ``"viewer"``, both, or none (a widget nothing says
    anything about, for example a custom one). Known from the draft's built-in lists and from any ``rdf:type``
    (``shui:Editor``/``shui:SingleEditor``/``shui:MultiEditor`` or the viewer equivalents) in the given graphs."""
    roles: set[str] = set()
    if widget in _BUILTIN_EDITORS:
        roles.add("editor")
    if widget in _BUILTIN_VIEWERS:
        roles.add("viewer")
    for graph in graphs:
        if graph is None:
            continue
        if any((widget, RDF.type, cls) in graph for cls in _EDITOR_CLASSES):
            roles.add("editor")
        if any((widget, RDF.type, cls) in graph for cls in _VIEWER_CLASSES):
            roles.add("viewer")
    return roles


# Declarations that make a shape validate some nodes by itself. A probe copy of a shapes graph drops them: whether a
# node conforms *to* a shape (sh:node) does not depend on what the shape targets, and a targeted shape elsewhere in the
# graph is none of the probe's business (GitHub issue #130).
_TARGET_PREDICATES = (
    SH.targetNode, SH.targetClass, SH.targetSubjectsOf, SH.targetObjectsOf, SH.target, SH.targetWhere,
)


def _conforming_nodes(nodes: Any, shape: Any, *, base_graph: Any, shapes_graph: Any) -> frozenset:
    """The members of ``nodes`` (resources in ``base_graph``) that conform to ``shape`` (defined in ``shapes_graph``).

    One probe shape (``sh:targetNode`` each node, ``sh:node shape``) is validated, and a node fails only if the probe's
    own ``sh:node`` check reports it. Nothing else in ``shapes_graph`` counts: its other shapes are not validated
    (their targets are dropped from the copy, so they cost nothing and cannot crash) and any result of theirs is
    ignored (the whole report's ``conforms`` is not used). ``owl:imports`` in ``shapes_graph`` is left unresolved
    (it plays no part in the check). Built on ``starlayer.shacl``'s public ``validate()``.
    """
    from rdflib import OWL

    from starlayer.graph.graph.starlayer_graph import StarLayerGraph
    from starlayer.shacl.validator import _find_genuine_report_node

    nodes = tuple(nodes)
    probe_shapes = StarLayerGraph()
    probe_shapes += shapes_graph
    for predicate in (*_TARGET_PREDICATES, OWL.imports):
        probe_shapes.remove((None, predicate, None))
    wrapper = BNode()
    probe_shapes.add((wrapper, RDF.type, SH.NodeShape))
    probe_shapes.add((wrapper, SH.node, shape))
    for node in nodes:
        probe_shapes.add((wrapper, SH.targetNode, node))
    result = validate(base_graph, probe_shapes, meta_shacl=False, ignore_imports=True)
    violating: set[Any] = set()
    report_node = _find_genuine_report_node(result.report_graph)
    if report_node is not None:
        for result_node in result.report_graph.objects(report_node, SH.result):
            if wrapper in set(result.report_graph.objects(result_node, SH.sourceShape)):
                violating.update(result.report_graph.objects(result_node, SH.focusNode))
    return frozenset(n for n in nodes if n not in violating)


def _node_conforms(node: Any, shape: Any, *, base_graph: Any, shapes_graph: Any) -> bool:
    """True iff ``node`` (a resource in ``base_graph``) conforms to ``shape`` (a shape already defined somewhere in
    ``shapes_graph``). The same answer :class:`_ConformanceBatch` gives for it, see :func:`_conforming_nodes`."""
    return node in _conforming_nodes((node,), shape, base_graph=base_graph, shapes_graph=shapes_graph)


class _ConformanceBatch:
    """Answers "does ``node`` conform to ``shape``?" for a fixed set of ``nodes`` with one ``validate()`` per distinct
    ``shape`` instead of one per (node, shape) pair.

    ``select_widgets`` asks the same matcher shapes about every property shape of a node shape. Each single check
    re-encodes the whole shapes graph, which dominated its cost (GitHub issue #14). Here all the nodes are targets
    of one probe shape, so the graph is encoded once per matcher shape. The answer for a node is the same as
    :func:`_node_conforms` gives for it alone.
    """

    def __init__(self, nodes: Any, *, base_graph: Any, shapes_graph: Any) -> None:
        self._nodes = tuple(nodes)
        self._base_graph = base_graph
        self._shapes_graph = shapes_graph
        self._conforming: dict[Any, frozenset] = {}

    def conforms(self, node: Any, shape: Any) -> bool:
        if node not in self._nodes:
            return _node_conforms(node, shape, base_graph=self._base_graph, shapes_graph=self._shapes_graph)
        if shape not in self._conforming:
            self._conforming[shape] = _conforming_nodes(
                self._nodes, shape, base_graph=self._base_graph, shapes_graph=self._shapes_graph
            )
        return node in self._conforming[shape]


def _find_matcher(widget: Any, scoring_graph: Any) -> Any | None:
    """The ``shui:WidgetAcceptMatcher`` naming ``widget`` via its own
    ``shui:widget`` value(s), or ``None`` if ``widget`` has none - no
    cardinality assumed on either side (see module docstring)."""
    for matcher in scoring_graph.subjects(SHUI.widget, widget):
        if (matcher, RDF.type, SHUI.WidgetAcceptMatcher) in scoring_graph:
            return matcher
    return None


def _shape_condition_holds(
    node: Any, *, shape_node: Any, shapes_graph: Any, scoring_graph: Any, batch: _ConformanceBatch | None = None
) -> bool:
    """The ``shui:shapesGraphShape`` of ``node`` (a score or a matcher): the shape node is validated in the *shapes
    graph* against it, its definition read from the *scoring graph*. True if ``node`` has none. Independent of the
    focus node, so the answer is the same for every node of the same shape."""
    shapes_graph_shape = next(scoring_graph.objects(node, SHUI.shapesGraphShape), None)
    if shapes_graph_shape is None:
        return True
    if batch is not None:
        return batch.conforms(shape_node, shapes_graph_shape)
    return _node_conforms(shape_node, shapes_graph_shape, base_graph=shapes_graph, shapes_graph=scoring_graph)


def _data_condition_holds(
    node: Any, *, focus_node: Any, data_graph: Any, shapes_graph: Any, scoring_graph: Any
) -> bool:
    """The ``shui:dataGraphShape`` of ``node``: the focus node is validated in the *data graph* against it. The spec
    reads that shape from the shapes graph; the scoring graph is searched too, so a catalog that defines it beside the
    score also works. True if ``node`` has none."""
    data_graph_shape = next(scoring_graph.objects(node, SHUI.dataGraphShape), None)
    if data_graph_shape is None:
        return True
    from starlayer.graph.graph.starlayer_graph import StarLayerGraph

    shape_definitions = StarLayerGraph()
    shape_definitions += shapes_graph
    shape_definitions += scoring_graph
    return _node_conforms(focus_node, data_graph_shape, base_graph=data_graph, shapes_graph=shape_definitions)


def _matcher_accepts(
    matcher: Any,
    *,
    shape_node: Any,
    focus_node: Any | None,
    data_graph: Any | None,
    shapes_graph: Any,
    scoring_graph: Any,
    batch: _ConformanceBatch | None = None,
) -> bool:
    """Section 3.4 Matcher Function, step for step:

    1. No focus node, a ``shui:dataGraphShape`` present and no
       ``shui:shapesGraphShape``: reject - the only condition cannot be checked.
    2. The shape node is validated in the *shapes graph* against the
       matcher's ``shui:shapesGraphShape``. Reject on failure.
    3. No focus node: accept.
    4. The focus node is validated in the *data graph* against the
       matcher's ``shui:dataGraphShape``.
    """
    has_shape_condition = next(scoring_graph.objects(matcher, SHUI.shapesGraphShape), None) is not None
    has_data_condition = next(scoring_graph.objects(matcher, SHUI.dataGraphShape), None) is not None

    if focus_node is None and has_data_condition and not has_shape_condition:
        return False
    if not _shape_condition_holds(
        matcher, shape_node=shape_node, shapes_graph=shapes_graph, scoring_graph=scoring_graph, batch=batch
    ):
        return False
    if focus_node is None:
        return True
    return _data_condition_holds(
        matcher, focus_node=focus_node, data_graph=data_graph, shapes_graph=shapes_graph, scoring_graph=scoring_graph
    )


def _ranked_scores(shapes_graph: Any, scoring_graph: Any, role: str) -> list[tuple[float, Any, Any]]:
    """Every ``shui:WidgetScore`` with a widget and a score whose widget can have this role, as ``(score, widget,
    score node)``, highest score first and then by widget IRI codepoints (Section 3.5 step 2)."""
    ranked: list[tuple[float, Any, Any]] = []
    for score_node in scoring_graph.subjects(RDF.type, SHUI.WidgetScore):
        widget = next(scoring_graph.objects(score_node, SHUI.widget), None)
        score_value = next(scoring_graph.objects(score_node, SHUI.score), None)
        if widget is None or score_value is None:
            continue
        roles = _widget_roles(widget, scoring_graph, shapes_graph)
        if roles and role not in roles:
            continue  # a widget known only as the other role is not a candidate (draft Sections 4.1 and 4.2)
        try:
            score = float(score_value)
        except (TypeError, ValueError):
            continue  # a score that is not a number is skipped, like a score node with no widget or no value
        ranked.append((score, widget, score_node))
    ranked.sort(key=lambda entry: (-entry[0], str(entry[1])))
    return ranked


def select_widget(
    *,
    shape_node: Any,
    focus_node: Any | None = None,
    data_graph: Any | None = None,
    shapes_graph: Any,
    scoring_graph: Any | None = None,
    role: Role,
    _batch: _ConformanceBatch | None = None,
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
    3. Walk that ranked list and return the first entry whose conditions hold: the
       ``shui:shapesGraphShape`` / ``shui:dataGraphShape`` written on the score itself (none means it applies
       to everything), and then, if its widget has a ``shui:WidgetAcceptMatcher``, that matcher too.
       Conditions on a score are local to it, so a catalog layered on top can add a score for a widget another
       layer conditioned without having to remove anything; a per-widget matcher is shared by every layer.

    Returns ``None`` if nothing matches at all. ``data_graph``/
    ``shapes_graph``/``scoring_graph`` may be the same object - the spec
    doesn't require them to be separate graphs, just separate *roles*.

    ``focus_node`` and ``data_graph`` are optional. They are used only to
    check a matcher's ``shui:dataGraphShape``. With no ``focus_node`` a matcher
    that has only a data condition rejects its widget (Section 3.4 step 1),
    while one with a ``shui:shapesGraphShape`` is decided by that alone, so
    the choice is per shape rather than per node. Passing a ``focus_node``
    without a ``data_graph`` raises ``ValueError``.

    **``role`` limits the candidates in the scoring catalog to that role.** The draft's Select Function
    (Section 3.2) takes a widget predicate and its Score Function (Section 3.5) lists every ``shui:WidgetScore``
    without a type, but Sections 4.1 and 4.2 say an editor is chosen for ``shui:editor`` and a viewer for
    ``shui:viewer``. A widget counts as an editor if it is one of the draft's built-in editors (Section 9.1) or the
    catalog or shapes graph types it ``shui:Editor`` (or ``shui:SingleEditor``/``shui:MultiEditor``), and as a
    viewer likewise (Section 9.2). A widget with no known role, such as a custom one, is a candidate for both. A
    widget the shape names itself with ``shui:editor``/``shui:viewer`` is not checked. So a property with only
    viewers in the catalog gets ``None`` for ``role="editor"`` (GitHub issue #9).

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
            batch=_batch,
        ):
            return explicit_widget

    ranked = _ranked_scores(shapes_graph, scoring_graph, role)

    common = {
        "shape_node": shape_node,
        "focus_node": focus_node,
        "data_graph": data_graph,
        "shapes_graph": shapes_graph,
        "scoring_graph": scoring_graph,
        "batch": _batch,
    }
    for _score, widget, score_node in ranked:
        # A condition written on the score itself (shui:shapesGraphShape / shui:dataGraphShape, as the Working
        # Group's own widget files do) applies to that score only. A score without one applies to everything.
        if not _matcher_accepts(score_node, **common):
            continue
        matcher = _find_matcher(widget, scoring_graph)
        if matcher is None or _matcher_accepts(matcher, **common):
            return widget

    return None


@dataclass(frozen=True)
class WidgetCandidate:
    """A widget that could be chosen for a property shape, found without looking at any node's data.

    ``score`` is ``None`` when the shape names the widget itself (a preference). ``data_checks`` lists the conditions
    that still need a focus node: ``(node, has_shape_condition)`` for each score or matcher that carries a
    ``shui:dataGraphShape``. A candidate with none applies to every node."""

    widget: URIRef
    score: float | None
    data_checks: tuple[tuple[Any, bool], ...] = ()

    @property
    def needs_data(self) -> bool:
        return bool(self.data_checks)


@dataclass(frozen=True)
class WidgetChoice:
    """The answer for one property shape, computed once and good for every node of that shape.

    ``candidates`` are in rank order and end at the first one that needs no data (nothing below it can win), so the
    list is short. The shape conditions (``shui:shapesGraphShape``) are already settled, which is the expensive part;
    finishing the choice for one node (:func:`check_data_matchers`) validates only the conditions that read data.

    ``needs_data`` False means the answer is the same for every node: keep ``widget_without_data`` and never look at
    a node again."""

    property_shape: Any
    candidates: tuple[WidgetCandidate, ...]
    _shapes_graph: Any = field(default=None, repr=False, compare=False)
    _scoring_graph: Any = field(default=None, repr=False, compare=False)

    @property
    def needs_data(self) -> bool:
        return any(candidate.needs_data for candidate in self.candidates)

    @property
    def widget_without_data(self) -> URIRef | None:
        """What :func:`select_widget` gives with no focus node (Section 3.4 steps 1 and 3): a candidate whose data
        conditions all sit beside a shape condition is accepted, one with a data condition alone is rejected."""
        for candidate in self.candidates:
            if all(has_shape_condition for _node, has_shape_condition in candidate.data_checks):
                return candidate.widget
        return None

    def resolve(self, focus_node: Any, data_graph: Any) -> URIRef | None:
        """The widget for one node: see :func:`check_data_matchers`."""
        return check_data_matchers(self, focus_node=focus_node, data_graph=data_graph)


def check_data_matchers(choice: WidgetChoice, *, focus_node: Any, data_graph: Any) -> URIRef | None:
    """Finish a per-shape choice for one node: the first candidate whose data conditions hold for ``focus_node`` in
    ``data_graph``. Gives the same widget as ``select_widget`` with that focus node, but validates only the few
    conditions that read data (GitHub issue #14)."""
    for candidate in choice.candidates:
        if all(
            _data_condition_holds(
                node,
                focus_node=focus_node,
                data_graph=data_graph,
                shapes_graph=choice._shapes_graph,
                scoring_graph=choice._scoring_graph,
            )
            for node, _has_shape_condition in candidate.data_checks
        ):
            return candidate.widget
    return None


def _candidate(widget: Any, score: float | None, nodes: list[Any], *, shape_node: Any, shapes_graph: Any,
               scoring_graph: Any, batch: _ConformanceBatch | None) -> WidgetCandidate | None:
    """``None`` if a shape condition of any of ``nodes`` fails; otherwise the candidate with its data conditions left."""
    checks = []
    for node in nodes:
        if not _shape_condition_holds(
            node, shape_node=shape_node, shapes_graph=shapes_graph, scoring_graph=scoring_graph, batch=batch
        ):
            return None
        if next(scoring_graph.objects(node, SHUI.dataGraphShape), None) is not None:
            has_shape_condition = next(scoring_graph.objects(node, SHUI.shapesGraphShape), None) is not None
            checks.append((node, has_shape_condition))
    return WidgetCandidate(widget=widget, score=score, data_checks=tuple(checks))


def _choice_for_property(
    property_shape: Any, *, shapes_graph: Any, scoring_graph: Any, role: str, batch: _ConformanceBatch | None
) -> WidgetChoice:
    common = {"shape_node": property_shape, "shapes_graph": shapes_graph, "scoring_graph": scoring_graph, "batch": batch}
    candidates: list[WidgetCandidate] = []
    predicate = SHUI.editor if role == "editor" else SHUI.viewer
    preferred = next(shapes_graph.objects(property_shape, predicate), None)
    if preferred is not None:
        matcher = _find_matcher(preferred, scoring_graph)
        candidate = _candidate(preferred, None, [matcher] if matcher is not None else [], **common)
        if candidate is not None:
            candidates.append(candidate)
    if not candidates or candidates[-1].needs_data:
        for score, widget, score_node in _ranked_scores(shapes_graph, scoring_graph, role):
            matcher = _find_matcher(widget, scoring_graph)
            candidate = _candidate(widget, score, [score_node] + ([matcher] if matcher is not None else []), **common)
            if candidate is None:
                continue
            candidates.append(candidate)
            if not candidate.needs_data:
                break
    return WidgetChoice(
        property_shape=property_shape,
        candidates=tuple(candidates),
        _shapes_graph=shapes_graph,
        _scoring_graph=scoring_graph,
    )


def select_widgets(
    *,
    shape_node: Any,
    focus_node: Any | None = None,
    data_graph: Any | None = None,
    shapes_graph: Any,
    scoring_graph: Any | None = None,
    role: Role,
    per: Literal["node", "shape"] = "node",
) -> dict[Any, Any]:
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

    **``per="shape"``** (GitHub issue #14) answers once per property shape instead of once per node, for a UI that
    shows many nodes of the same shape. It returns ``{property_shape: WidgetChoice}``; the expensive checks (a
    condition's ``shui:shapesGraphShape``) are done once, and ``choice.resolve(focus_node, data_graph)`` finishes the
    choice for one node by validating only the conditions that read its data. ``choice.needs_data`` False means one
    answer (``choice.widget_without_data``) serves every node. The result of ``resolve`` is the same as
    ``select_widget`` with that node. ``focus_node`` and ``data_graph`` are not accepted with ``per="shape"``.
    """
    if per not in ("node", "shape"):
        raise ValueError("per must be 'node' or 'shape'")
    if per == "shape" and (focus_node is not None or data_graph is not None):
        raise ValueError("per='shape' answers for the shape; pass the node to choice.resolve(focus_node, data_graph)")
    properties = list(shapes_graph.objects(shape_node, SH.property))
    if scoring_graph is None:
        from starlayer.graph.graph.starlayer_graph import StarLayerGraph

        scoring_graph = StarLayerGraph()
    batch = _ConformanceBatch(properties, base_graph=shapes_graph, shapes_graph=scoring_graph)
    if per == "shape":
        return {
            prop: _choice_for_property(prop, shapes_graph=shapes_graph, scoring_graph=scoring_graph, role=role, batch=batch)
            for prop in properties
        }
    result: dict[Any, Any] = {}
    for prop in properties:
        result[prop] = select_widget(
            shape_node=prop, focus_node=focus_node,
            data_graph=data_graph, shapes_graph=shapes_graph, scoring_graph=scoring_graph, role=role,
            _batch=batch,
        )
    return result
