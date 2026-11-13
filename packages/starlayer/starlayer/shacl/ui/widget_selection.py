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

from dataclasses import dataclass, field, replace
from typing import Any, Literal

import pyoxigraph as ox

from starlayer.graph.core import StarLayerDataset, StarLayerGraph

# The terms are pyoxigraph terms. The graphs are read as they are (``StarLayerGraph`` / ``StarLayerDataset`` / ``pyoxigraph.Store``), with
# no copy; an rdflib graph or term is a ``TypeError``.
from starlayer.graph.namespaces import SHUI  # noqa: E402,F401
from starlayer.shacl.engine.terms import RDF, SH

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
_OWL_IMPORTS = ox.NamedNode("http://www.w3.org/2002/07/owl#imports")
_OX_TERMS = (ox.NamedNode, ox.BlankNode, ox.Literal, ox.Triple)


# ---- the boundary ------------------------------------------------------------------------------------------------------


def _as_ox_graph(value: Any) -> Any:
    """``value`` as something this module reads: ``StarLayerGraph`` / ``StarLayerDataset`` as they are, a ``pyoxigraph.Store`` as a
    dataset, ``None`` as an empty graph. An rdflib graph is a ``TypeError``."""
    if value is None:
        return StarLayerGraph()
    if isinstance(value, (StarLayerGraph, StarLayerDataset)):
        return value
    if isinstance(value, ox.Store):
        return StarLayerDataset(store=value)
    from starlayer.graph.inputs import as_oxigraph

    return as_oxigraph(value)  # raises the TypeError that points to from_rdflib


def _term_in(term: Any) -> Any:
    """A caller's node, which must be a pyoxigraph term (``None`` stays)."""
    if term is None or isinstance(term, _OX_TERMS):
        return term
    raise TypeError(f"a node must be a pyoxigraph term (NamedNode, BlankNode, Literal or Triple), not {type(term).__name__}")


class _Boundary:
    """What the public functions do with their arguments: nodes and graphs are pyoxigraph / StarLayer objects, and the answer is in pyoxigraph terms."""

    def __init__(self, shape_node: Any, focus_node: Any, shapes_graph: Any, scoring_graph: Any) -> None:
        self.shape_node = _term_in(shape_node)
        self.focus_node = _term_in(focus_node)
        self.shapes_graph = _as_ox_graph(shapes_graph)
        self.scoring_graph = self.shapes_graph if scoring_graph is shapes_graph and scoring_graph is not None else _as_ox_graph(scoring_graph)

    @staticmethod
    def out(term: Any) -> Any:
        return term

    @staticmethod
    def choice_out(choice: WidgetChoice) -> WidgetChoice:
        return choice


def _conformance_context(base_graph: Any, shapes_graph: Any) -> Any:
    """What answers "does this node conform to this shape?" directly: the shapes graph's plan (a shape is built the first time it is asked about) over ``base_graph``."""
    from starlayer.shacl.engine.executor import Context
    from starlayer.shacl.engine.plan import Plan

    return Context(data=base_graph, plan=Plan(shapes_graph=shapes_graph))


def _conforming_nodes(nodes: Any, shape: Any, *, base_graph: Any, shapes_graph: Any, context: Any = None) -> frozenset:
    """The members of ``nodes`` (resources in ``base_graph``) that conform to ``shape`` (defined in ``shapes_graph``).

    Only ``shape`` and what it reaches are looked at: no other shape of ``shapes_graph`` is built or validated, no report
    is made, and ``owl:imports`` plays no part. Asked of the engine's own conformance check, not of ``validate()``: a
    full validation copied the shapes graph, rebuilt its plan and built a report for what is one yes/no answer.
    """
    context = context or _conformance_context(base_graph, shapes_graph)
    return frozenset(n for n in tuple(nodes) if context.conforms(shape, n))


def _node_conforms(node: Any, shape: Any, *, base_graph: Any, shapes_graph: Any) -> bool:
    """True iff ``node`` (a resource in ``base_graph``) conforms to ``shape`` (a shape already defined somewhere in
    ``shapes_graph``). The same answer :class:`_ConformanceBatch` gives for it, see :func:`_conforming_nodes`."""
    return node in _conforming_nodes((node,), shape, base_graph=base_graph, shapes_graph=shapes_graph)


class _ConformanceBatch:
    """Answers "does ``node`` conform to ``shape``?" for the nodes of one ``select_widgets`` call.

    ``select_widgets`` asks the same matcher shapes about every property shape of a node shape. One plan over the
    shapes graph (the catalog) and one conformance context over the base graph serve all the questions, so a matcher
    shape is built once and a (shape, node) answer is remembered (GitHub issue #14). The answer for a node is the same as
    :func:`_node_conforms` gives for it alone.
    """

    def __init__(self, nodes: Any, *, base_graph: Any, shapes_graph: Any) -> None:
        self._nodes = tuple(nodes)
        self._base_graph = base_graph
        self._shapes_graph = shapes_graph
        self._context = _conformance_context(base_graph, shapes_graph)
        self._conforming: dict[Any, frozenset] = {}

    def conforms(self, node: Any, shape: Any) -> bool:
        if node not in self._nodes:
            return _node_conforms(node, shape, base_graph=self._base_graph, shapes_graph=self._shapes_graph)
        if shape not in self._conforming:
            self._conforming[shape] = _conforming_nodes(
                self._nodes, shape, base_graph=self._base_graph, shapes_graph=self._shapes_graph, context=self._context
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
    shape_definitions = StarLayerGraph()
    shape_definitions.extend(iter(shapes_graph))
    shape_definitions.extend(iter(scoring_graph))
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
            score = _as_float(score_value)
        except (TypeError, ValueError):
            continue  # a score that is not a number is skipped, like a score node with no widget or no value
        ranked.append((score, widget, score_node))
    ranked.sort(key=lambda entry: (-entry[0], entry[1].value))
    return ranked


def _as_float(term: Any) -> float:
    """``float`` of a literal by its lexical form (``ValueError`` for text that is not a number, an IRI included)."""
    return float(term.value)


DEFAULT_WIDGET_SCORE = 40.0   # SHACL UI 4.3: the score D of a widget a shape names and the scoring graph does not score, when the configuration gives none


def default_widget_score(shapes_graph: Any) -> float:
    """The score D of a widget a shape names with ``shui:editor`` or ``shui:viewer`` that the scoring graph does not score (SHACL UI 4.3): the
    ``shui:defaultWidgetScore`` of the global configuration (a node of ``shapes_graph``; with several, the first by IRI), else 40."""
    for _node, value in sorted(_as_ox_graph(shapes_graph).subject_objects(SHUI.defaultWidgetScore), key=lambda pair: (pair[0].value, pair[1].value)):
        try:
            return _as_float(value)
        except (TypeError, ValueError):
            continue
    return DEFAULT_WIDGET_SCORE


def _ranked_with_declared(shape_node: Any, shapes_graph: Any, scoring_graph: Any, role: str) -> list[tuple[float, Any, Any]]:
    """The scoring graph's scores and, for each widget ``shape_node`` names itself that the scoring graph does not score, a score of ``default_widget_score``
    (SHACL UI 4.3, the preparation of the scoring graph; it has no score node, and its condition, that the shape names the widget, holds for this shape).
    Highest score first, then by widget IRI."""
    ranked = _ranked_scores(shapes_graph, scoring_graph, role)
    predicate = SHUI.editor if role == "editor" else SHUI.viewer
    scored = {widget for node in scoring_graph.subjects(RDF.type, SHUI.WidgetScore) for widget in scoring_graph.objects(node, SHUI.widget)}
    declared = [w for w in shapes_graph.objects(shape_node, predicate) if isinstance(w, ox.NamedNode) and w not in scored]
    if declared:
        d = default_widget_score(shapes_graph)
        ranked = sorted([*ranked, *((d, widget, None) for widget in declared)], key=lambda entry: (-entry[0], entry[1].value))
    return ranked


@dataclass(frozen=True)
class WidgetReport:
    """What the SHACL UI draft makes an implementation tell its application (Section 3, "Scoring System"): "When a widget that the
    implementation does not implement matches, or when no widget matches, the implementation MUST report this to the application."

    ``kind`` is ``"unimplemented"`` (``widget`` matched but is not in ``implemented``, so it was not selected) or ``"none"`` (no widget
    the application implements matched). ``shape_node`` is the property shape, ``role`` ``"editor"`` or ``"viewer"``, ``score`` the
    unimplemented widget's score, ``focus_node`` the node when the choice was for one. How the report is handled or presented is left
    to the application."""

    kind: Literal["unimplemented", "none"]
    shape_node: Any
    role: str
    widget: Any | None = None
    score: float | None = None
    focus_node: Any | None = None


def _implemented_in(implemented: Any) -> frozenset | None:
    """``None`` (every widget is implemented) or the set of widget IRIs as pyoxigraph terms; a ``str`` is an IRI."""
    if implemented is None:
        return None
    return frozenset(ox.NamedNode(w) if isinstance(w, str) else _term_in(w) for w in implemented)


def _reporter(on_report: Any, boundary: Any) -> Any:
    """A function that sends a report to ``on_report`` with its terms in the caller's term family, or ``None`` without a callback."""
    if on_report is None:
        return None

    def report(r: WidgetReport) -> None:
        on_report(WidgetReport(
            kind=r.kind, shape_node=boundary.out(r.shape_node), role=r.role,
            widget=None if r.widget is None else boundary.out(r.widget), score=r.score,
            focus_node=None if r.focus_node is None else boundary.out(r.focus_node),
        ))

    return report


def select_widget(
    *,
    shape_node: Any,
    focus_node: Any | None = None,
    data_graph: Any | None = None,
    shapes_graph: Any,
    scoring_graph: Any | None = None,
    role: Role,
    implemented: Any | None = None,
    on_report: Any | None = None,
) -> Any | None:
    """Select the ``shui:editor``/``shui:viewer`` widget ``shape_node``
    should use for ``focus_node``, per the spec's own Section 3.2 "Select
    Function" procedure:

    1. Prepare the scores (SHACL UI 4.3): for each widget ``shape_node`` names with ``shui:editor``/``shui:viewer`` that no
       ``shui:WidgetScore`` of ``scoring_graph`` is for, add a score of ``default_widget_score`` (the ``shui:defaultWidgetScore`` of the
       configuration in ``shapes_graph``, else 40). A widget the scoring graph scores at all keeps only its own scores, whether or not they
       cover this shape (the draft says so).
    2. Collect every ``shui:WidgetScore`` in ``scoring_graph`` with both a ``shui:widget`` and a ``shui:score``, with those added,
       ranked highest-score-first and then by widget IRI.
    3. Walk that ranked list and return the first entry whose conditions hold: the
       ``shui:shapesGraphShape`` / ``shui:dataGraphShape`` written on the score itself (none means it applies
       to everything, as an added score does for this shape), and then, if its widget has a ``shui:WidgetAcceptMatcher``, that matcher too.
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

    **``implemented``** is the widgets the application can render (an iterable of widget IRIs). "An implementation MUST NOT select or offer
    a widget that it does not implement" (SHACL UI, Scoring System): a widget outside it is never returned, and the walk goes on to the
    next-ranked widget. ``None`` (the default) means every widget is implemented. **``on_report``** is a callable that receives a
    :class:`WidgetReport` for each unimplemented widget that matched and, when nothing is returned, one of kind ``"none"``: "the
    implementation MUST report this to the application". Without it nothing is reported.
    """
    if role not in ("editor", "viewer"):
        raise ValueError(f"role must be 'editor' or 'viewer', got {role!r}")
    if focus_node is not None and data_graph is None:
        raise ValueError("focus_node needs a data_graph to check its shui:dataGraphShape against")
    b = _Boundary(shape_node, focus_node, shapes_graph, scoring_graph)
    return b.out(_select(b.shape_node, b.focus_node, data_graph, b.shapes_graph, b.scoring_graph, role, None,
                         _implemented_in(implemented), _reporter(on_report, b)))


def _select(shape_node: Any, focus_node: Any, data_graph: Any, shapes_graph: Any, scoring_graph: Any, role: str,
            batch: _ConformanceBatch | None, implemented: frozenset | None = None, report: Any = None) -> Any | None:
    ranked = _ranked_with_declared(shape_node, shapes_graph, scoring_graph, role)

    common = {
        "shape_node": shape_node,
        "focus_node": focus_node,
        "data_graph": data_graph,
        "shapes_graph": shapes_graph,
        "scoring_graph": scoring_graph,
        "batch": batch,
    }
    for _score, widget, score_node in ranked:
        # A condition written on the score itself (shui:shapesGraphShape / shui:dataGraphShape, as the Working
        # Group's own widget files do) applies to that score only. A score without one applies to everything.
        if score_node is not None and not _matcher_accepts(score_node, **common):
            continue
        matcher = _find_matcher(widget, scoring_graph)
        if matcher is None or _matcher_accepts(matcher, **common):
            if implemented is not None and widget not in implemented:
                if report is not None:
                    report(WidgetReport("unimplemented", shape_node, role, widget, _score, focus_node))
                continue  # never select a widget the application does not implement; the next-ranked one may do
            return widget

    if report is not None:
        report(WidgetReport("none", shape_node, role, None, None, focus_node))
    return None


@dataclass(frozen=True)
class WidgetCandidate:
    """A widget that could be chosen for a property shape, found without looking at any node's data.

    ``score`` is the score the widget ranks with (``default_widget_score`` for a widget the shape names and the scoring graph does not score). ``data_checks`` lists the conditions
    that still need a focus node: ``(node, has_shape_condition)`` for each score or matcher that carries a
    ``shui:dataGraphShape``. A candidate with none applies to every node."""

    widget: ox.NamedNode
    score: float
    data_checks: tuple[tuple[Any, bool], ...] = ()
    implemented: bool = True  # False: the application does not implement the widget, so it is reported and never chosen

    @property
    def needs_data(self) -> bool:
        """Whether choosing this widget for a node depends on that node's data."""
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
    _role: str = field(default="", repr=False, compare=False)
    _report: Any = field(default=None, repr=False, compare=False)

    @property
    def needs_data(self) -> bool:
        """Whether the widget can differ between nodes of this shape, so each node must be checked."""
        return any(candidate.needs_data for candidate in self.candidates)

    @property
    def widget_without_data(self) -> ox.NamedNode | None:
        """What :func:`select_widget` gives with no focus node (Section 3.4 steps 1 and 3): a candidate whose data
        conditions all sit beside a shape condition is accepted, one with a data condition alone is rejected."""
        for candidate in self.candidates:
            if candidate.implemented and all(has_shape_condition for _node, has_shape_condition in candidate.data_checks):
                return candidate.widget
        return None

    def resolve(self, focus_node: Any, data_graph: Any) -> ox.NamedNode | None:
        """The widget for one node: see :func:`check_data_matchers`."""
        return check_data_matchers(self, focus_node=focus_node, data_graph=data_graph)


def check_data_matchers(choice: WidgetChoice, *, focus_node: Any, data_graph: Any) -> ox.NamedNode | None:
    """Finish a per-shape choice for one node: the first candidate whose data conditions hold for ``focus_node`` in
    ``data_graph``. Gives the same widget as ``select_widget`` with that focus node, but validates only the few
    conditions that read data (GitHub issue #14)."""
    focus_node = _term_in(focus_node)
    report = choice._report
    for candidate in choice.candidates:
        if all(
            _data_condition_holds(
                _term_in(node),
                focus_node=focus_node,
                data_graph=data_graph,
                shapes_graph=choice._shapes_graph,
                scoring_graph=choice._scoring_graph,
            )
            for node, _has_shape_condition in candidate.data_checks
        ):
            if not candidate.implemented:
                if report is not None:
                    report(WidgetReport("unimplemented", choice.property_shape, choice._role, candidate.widget, candidate.score, focus_node))
                continue
            return candidate.widget
    if report is not None:
        report(WidgetReport("none", choice.property_shape, choice._role, None, None, focus_node))
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
    property_shape: Any, *, shapes_graph: Any, scoring_graph: Any, role: str, batch: _ConformanceBatch | None,
    implemented: frozenset | None = None, report: Any = None,
) -> WidgetChoice:
    common = {"shape_node": property_shape, "shapes_graph": shapes_graph, "scoring_graph": scoring_graph, "batch": batch}
    candidates: list[WidgetCandidate] = []
    for score, widget, score_node in _ranked_with_declared(property_shape, shapes_graph, scoring_graph, role):
        matcher = _find_matcher(widget, scoring_graph)
        candidate = _candidate(widget, score, ([score_node] if score_node is not None else []) + ([matcher] if matcher is not None else []), **common)
        if candidate is None:
            continue
        if implemented is not None and widget not in implemented:
            if not candidate.needs_data:  # it matches every node: report it now, once for the shape
                if report is not None:
                    report(WidgetReport("unimplemented", property_shape, role, widget, score))
                continue
            candidate = replace(candidate, implemented=False)  # whether it matches depends on the node: decided in resolve()
        candidates.append(candidate)
        if not candidate.needs_data:
            break
    if not candidates and report is not None:  # nothing can match any node
        report(WidgetReport("none", property_shape, role))
    return WidgetChoice(
        property_shape=property_shape,
        candidates=tuple(candidates),
        _shapes_graph=shapes_graph,
        _scoring_graph=scoring_graph,
        _role=role,
        _report=report,
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
    implemented: Any | None = None,
    on_report: Any | None = None,
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

    **``implemented``** and **``on_report``** are as for :func:`select_widget`: a widget the application does not implement is never
    chosen, and the application is told (a :class:`WidgetReport`) when such a widget matched and when no widget matches. With
    ``per="shape"`` a widget whose matching depends on the node is reported by ``choice.resolve(focus_node, data_graph)``, the others
    when the choice is made.
    """
    if per not in ("node", "shape"):
        raise ValueError("per must be 'node' or 'shape'")
    if role not in ("editor", "viewer"):
        raise ValueError(f"role must be 'editor' or 'viewer', got {role!r}")
    b = _Boundary(shape_node, focus_node, shapes_graph, scoring_graph)
    shapes, scoring = b.shapes_graph, b.scoring_graph
    if (b.shape_node, None, None) not in shapes:
        raise ValueError(f"shape_node {shape_node!r} is not a subject in the shapes graph")
    if per == "shape" and (focus_node is not None or data_graph is not None):
        raise ValueError("per='shape' answers for the shape; pass the node to choice.resolve(focus_node, data_graph)")
    properties = list(shapes.objects(b.shape_node, SH.property))
    if properties and focus_node is not None and data_graph is None:
        raise ValueError("focus_node needs a data_graph to check its shui:dataGraphShape against")
    batch = _ConformanceBatch(properties, base_graph=shapes, shapes_graph=scoring)
    implemented_set, report = _implemented_in(implemented), _reporter(on_report, b)
    if per == "shape":
        return {
            b.out(prop): b.choice_out(
                _choice_for_property(
                    prop, shapes_graph=shapes, scoring_graph=scoring, role=role, batch=batch,
                    implemented=implemented_set, report=report,
                )
            )
            for prop in properties
        }
    return {
        b.out(prop): b.out(_select(prop, b.focus_node, data_graph, shapes, scoring, role, batch, implemented_set, report))
        for prop in properties
    }


@dataclass(frozen=True)
class WidgetCondition:
    """One condition a widget candidate has: its ``kind`` (``"score"``: the ``shui:WidgetScore``; ``"matcher"``: the widget's ``shui:WidgetAcceptMatcher``) and ``node``.

    ``shape`` is the node's ``shui:shapesGraphShape`` and ``shape_holds`` whether the property shape conforms to it (``None`` without one).
    ``data_shape`` is its ``shui:dataGraphShape`` and ``data_holds`` how many of the sampled focus nodes conform, as ``(conforming, sampled)``
    (``None`` without a data shape, a sample or a data graph). ``blocks`` says what stops the candidate: ``"shape"`` (the shape condition fails),
    ``"data"`` (a data condition stands alone, which cannot be checked without a node) or ``None``."""

    kind: str
    node: Any
    shape: Any | None
    shape_holds: bool | None
    data_shape: Any | None
    data_holds: tuple[int, int] | None
    blocks: str | None


@dataclass(frozen=True)
class WidgetTraceCandidate:
    """A widget the selection considers, in rank order. ``scored`` is False for a widget the shape names that the scoring graph does not
    score (it ranks with ``default_score``). ``outcome``: ``"rejected"`` (a condition blocks it), ``"per node"`` (data conditions beside
    shape conditions that hold: decided for each node) or ``"accepted"``."""

    widget: Any
    score: float
    scored: bool
    conditions: tuple[WidgetCondition, ...]
    outcome: str


@dataclass(frozen=True)
class WidgetTrace:
    """Why a property shape gets the widget it gets: ``named`` are the widgets the shape names itself (``shui:editor`` / ``shui:viewer``), ``default_score`` is
    the score a named widget has when nothing scores it, and ``candidates`` are every widget considered, highest score first, with their conditions
    and outcome. The winner is the first candidate that is not rejected and, for a node, whose data conditions hold: ``select_widget`` makes that call."""

    shape_node: Any
    role: str
    default_score: float
    named: tuple[Any, ...]
    candidates: tuple[WidgetTraceCandidate, ...]


def explain_widgets(
    *, shape_node: Any, shapes_graph: Any, scoring_graph: Any | None = None, role: Role, data_graph: Any | None = None,
    focus_nodes: Any = (), sample: int = 3,
) -> WidgetTrace:
    """Every candidate widget for the property shape ``shape_node`` in ``role`` with the steps ``select_widget`` takes (SHACL UI 3.2 to 3.5), for a report.

    Nothing is chosen here; ``select_widget`` and ``select_widgets`` choose, and this says why. ``data_graph`` and ``focus_nodes`` are optional: with
    them, a data condition is tried on the first ``sample`` focus nodes and the count is in ``WidgetCondition.data_holds`` (a report of what is known,
    not a check: a data shape that cannot run is left unsaid). ``ValueError`` for a role that is not ``"editor"`` or ``"viewer"`` and for a
    ``shape_node`` that is not in the shapes graph."""
    if role not in ("editor", "viewer"):
        raise ValueError(f"role must be 'editor' or 'viewer', got {role!r}")
    b = _Boundary(shape_node, None, shapes_graph, scoring_graph)
    shapes, scoring, shape = b.shapes_graph, b.scoring_graph, b.shape_node
    if (shape, None, None) not in shapes:
        raise ValueError(f"shape_node {shape_node!r} is not a subject in the shapes graph")
    data = None if data_graph is None else _as_ox_graph(data_graph)
    focus = [_term_in(n) for n in list(focus_nodes)[:sample]] if data is not None else []
    named_predicate = SHUI.editor if role == "editor" else SHUI.viewer
    candidates = []
    for score, widget, score_node in _ranked_with_declared(shape, shapes, scoring, role):
        conditions = []
        for kind, node in (("score", score_node), ("matcher", _find_matcher(widget, scoring))):
            if node is None:
                continue
            shape_condition = next(scoring.objects(node, SHUI.shapesGraphShape), None)
            data_condition = next(scoring.objects(node, SHUI.dataGraphShape), None)
            holds = _shape_condition_holds(node, shape_node=shape, shapes_graph=shapes, scoring_graph=scoring) if shape_condition is not None else None
            counted = None
            if data_condition is not None and focus:
                try:
                    counted = (sum(1 for f in focus if _data_condition_holds(node, focus_node=f, data_graph=data, shapes_graph=shapes, scoring_graph=scoring)), len(focus))
                except Exception:  # noqa: BLE001  (a report of what is known, not a check)
                    counted = None
            blocks = "shape" if holds is False else ("data" if data_condition is not None and shape_condition is None else None)
            conditions.append(WidgetCondition(kind, node, shape_condition, holds, data_condition, counted, blocks))
        outcome = "rejected" if any(c.blocks for c in conditions) else ("per node" if any(c.data_shape is not None for c in conditions) else "accepted")
        candidates.append(WidgetTraceCandidate(widget, score, score_node is not None, tuple(conditions), outcome))
    named = tuple(sorted((w for w in shapes.objects(shape, named_predicate) if isinstance(w, ox.NamedNode)), key=lambda w: w.value))
    return WidgetTrace(shape, role, default_widget_score(shapes), named, tuple(candidates))
