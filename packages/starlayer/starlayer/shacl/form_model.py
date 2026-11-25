"""``form_model()``: what fields a node's form has, with what values, as one join of answers StarLayer already gives.

A form editor asks one question per node: which fields, in what order and sections, with which widget, which values and where each
value comes from. The answer is assembled from ``target_shapes`` (which shapes apply), the property shapes' own ``sh:name``,
``sh:description``, ``sh:order``, ``sh:group`` and ``sh:defaultValue`` (SHACL Core), ``select_widgets`` and ``shui:suggestedValues``
(SHACL UI), ``value_form``, ``evaluate`` (computed and default values), ``candidate_values``, ``check_value`` and a report the caller
passes. No vocabulary of its own is read except StarLayer's ``stsh:formHeldBy`` / ``stsh:formOnlyFor`` / ``stsh:secondary`` of the
``shacl_shacl_ui`` form shapes.

Rules that hold throughout:

- **The data graph may suggest, never decide.** Stored values and candidates come from the data; whether something is valid comes only
  from a report the caller passes in. The model never validates; ``FormField.check()`` validates one value when asked.
- **Several shapes for one node are merged by path**, one field per distinct ``sh:path`` term, with every contributing property shape
  kept in ``property_shapes`` (none is a witness for the others). Where one value is needed (name, description, order, group, widget,
  suggested values, the shape ``value_form`` and ``candidates`` read) the first contributing shape that has one gives it, shapes
  being ordered by their own ``sh:order`` (none last), then by IRI text. ``required`` is any ``sh:minCount`` above 0, ``max_count`` the
  smallest ``sh:maxCount``.
- **Reproducible**: no randomness; every ordering is stable and said where it is made.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from typing import Any, get_args

from starlayer.shacl.candidates import Candidates
from starlayer.shacl.engine.candidates import ordered
from starlayer.shacl.engine.components.core_value import alternatives, rdf_list
from starlayer.shacl.engine.deactivation import deactivated_at
from starlayer.shacl.engine.executor import Context, _deactivated
from starlayer.shacl.engine.paths import eval_path
from starlayer.shacl.engine.plan import SH, Plan
from starlayer.shacl.engine.terms import (
    NS,
    RDF,
    RDFS,
    BlankNode,
    Literal,
    NamedNode,
    engine_view,
    n3,
    text,
    to_engine,
)
from starlayer.shacl.report_results import ReportResult, report_results
from starlayer.shacl.ui.widget_selection import SHUI, Role, WidgetChoice, select_widgets
from starlayer.shacl.value_check import ValueCheck

STSH = NS("https://github.com/hidden-graph/starlayer/ns/shacl#")

_ROLES = get_args(Role)
_EMPTY = ("auto", "all", "none")
SOURCES = ("stored", "inferred", "computed", "default")
REASONS = ("inferred", "computed", "default", "path", "role", "no shape")


@dataclass(frozen=True)
class FieldConstraints:
    """The plain constraints of a field's property shape(s), terms and numbers, as the shapes state them.

    With several contributing shapes every constraint must hold, so the tuples hold the values of all of them (sorted: IRIs by text,
    then blank nodes, then literals), ``min_count`` / ``min_length`` are the largest and ``max_count`` / ``max_length`` the smallest,
    and ``in_values`` is the intersection of the ``sh:in`` lists, in the order of the first list. ``datatypes``, ``classes`` and
    ``node_kinds`` hold each alternative of a list value (``sh:datatype ( a b )`` is a union in SHACL 1.2). ``None`` and ``()`` mean the
    shapes say nothing. Nothing here is a judgment on a value: ``FormField.check()`` is."""

    datatypes: tuple[Any, ...] = ()
    classes: tuple[Any, ...] = ()
    node_kinds: tuple[Any, ...] = ()
    min_count: int | None = None
    max_count: int | None = None
    min_length: int | None = None
    max_length: int | None = None
    patterns: tuple[str, ...] = ()
    min_inclusive: tuple[Any, ...] = ()
    max_inclusive: tuple[Any, ...] = ()
    min_exclusive: tuple[Any, ...] = ()
    max_exclusive: tuple[Any, ...] = ()
    in_values: tuple[Any, ...] | None = None


@dataclass(frozen=True)
class FormValue:
    """One value of a field.

    ``source`` is ``"stored"`` (the data graph), ``"inferred"`` (found only in ``inferred_graph``), ``"computed"`` (``sh:values``) or
    ``"default"`` (``sh:defaultValue``, only when the field has no stored value: a suggestion, never a stored value). ``editable`` is
    True only for a stored value of an editable field. ``reason`` is None when editable, else the first that holds of ``"role"``
    (the form is a viewer's), ``"path"`` (the field's path is not a predicate or an inverse predicate), ``"no shape"`` (a stored value
    of a predicate no shape covers: ``FormModel.others``), or the value's own ``source`` for an inferred, computed or default value.

    ``members`` is for a field whose ``value_form`` is ``"list"`` or ``"single-or-list"``: when ``term`` heads a well-formed RDF list
    (``rdf:nil`` is the empty list) they are its members in the list's own order, else None. ``term`` stays the list head, one value."""

    term: Any
    source: str
    editable: bool
    reason: str | None
    members: tuple[Any, ...] | None = None


@dataclass(frozen=True)
class _CheckContext:
    data: Any
    shapes: Any
    node: Any
    subclass_of_in_shapes_graph: bool
    floor: Any


@dataclass(frozen=True)
class FormField:
    """One field of a form: a path with what the shapes say about it and the values the node has there.

    ``path`` is the ``sh:path`` term (a blank node for a complex path; ``editable`` is False then, see below). ``property_shapes`` are
    all the contributing property shapes in the order described in the module docstring (empty for a predicate in
    ``FormModel.others``). ``name`` and ``description`` are all the ``sh:name`` / ``sh:description`` literals of the first shape that
    has one, so the app picks the language. ``order`` is the first shape's ``sh:order`` (else ``shui:defaultOrder``, else None) as a
    float; ``group`` and ``group_order`` are its ``sh:group`` and that group's ``sh:order`` (else ``shui:defaultOrder``). ``widget`` is
    the widget for the form's role (``select_widgets``), None when none applies. ``values`` are in the order stored, inferred,
    computed, default; inside one source IRIs by text, then blank nodes, then literals by lexical form and datatype, then triple terms.

    ``value_form`` is ``"single"``, ``"list"`` or ``"single-or-list"`` (``value_form()`` of the first shape). ``editable`` is true for
    the role ``"editor"`` when the path is a predicate or an inverse predicate; a complex path (sequence, alternative, repeat, inverse
    of one) is read through ``path_values`` and its field is included, with every value not editable and the reason ``"path"``, so an
    app that cannot edit it filters on ``editable``. ``candidates`` is None unless the model was made with ``suggestions=True``;
    ``suggested`` are the ``shui:suggestedValues`` of the shape, in list order, and are not candidates. ``errors`` are the report's
    results for this node and path, None of them when no report was passed. ``secondary``: a property shape says ``stsh:secondary
    true``."""

    path: Any
    property_shapes: tuple[Any, ...]
    name: tuple[Any, ...]
    description: tuple[Any, ...]
    order: float | None
    widget: Any | None
    values: tuple[FormValue, ...]
    value_form: str
    required: bool
    max_count: int | None
    editable: bool
    candidates: Candidates | None
    suggested: tuple[Any, ...]
    errors: tuple[ReportResult, ...]
    secondary: bool
    constraints: FieldConstraints
    group: Any | None = None
    group_order: float | None = None
    _context: Any = field(default=None, repr=False, compare=False)

    def check(self, value: Any) -> ValueCheck:
        """Whether ``value`` would be accepted for this field of the node: ``check_value()`` on the first contributing property shape,
        on demand (nothing is computed up front). A ``ValueError`` for a field no shape covers or whose path cannot be written."""
        context: _CheckContext | None = self._context
        if context is None or not self.property_shapes:
            raise ValueError("this field has no property shape (no shape covers its predicate), so there is nothing to check a value against")
        from starlayer.shacl import _adapter

        return _adapter.check_value(
            data_graph=context.data,
            shacl_graph=context.shapes,
            property_shape=self.property_shapes[0],
            focus=context.node,
            value=value,
            subclass_of_in_shapes_graph=context.subclass_of_in_shapes_graph,
            conformance_disallows=context.floor,
        )


@dataclass(frozen=True)
class FormSection:
    """A group of fields. ``group`` is the ``sh:PropertyGroup`` (None for the ungrouped fields and for the collapsed section of
    secondary fields); ``label`` its ``sh:name`` literals, else its ``rdfs:label`` literals, for the app to pick a language from;
    ``order`` its ``sh:order`` (else ``shui:defaultOrder``). ``collapsed`` is True for the one section that holds the ``stsh:secondary``
    fields of the form, last, with no group and no label."""

    group: Any | None
    label: tuple[Any, ...]
    order: float | None
    fields: tuple[FormField, ...]
    collapsed: bool = False


@dataclass(frozen=True)
class FormModel:
    """The form of one node: ``shapes`` are the node shapes used (applicable ones, or the ones asked for), ``sections`` the fields the
    shapes describe, ``others`` the stored predicates of the node that no used shape covers (read only: every value has the reason
    ``"no shape"``, or ``"role"`` for a viewer; ``rdf:type`` is a field like any other when no shape covers it), in predicate IRI order.
    ``notes`` say what was left out or ignored; ``node_errors`` are the report's results about the node itself (no ``sh:resultPath``);
    ``hidden_empty`` counts the fields the ``empty`` setting left out."""

    node: Any
    role: str
    shapes: tuple[Any, ...]
    sections: tuple[FormSection, ...]
    others: tuple[FormField, ...]
    notes: tuple[str, ...]
    node_errors: tuple[ReportResult, ...]
    hidden_empty: int

    @property
    def fields(self) -> tuple[FormField, ...]:
        """The fields of the sections, flattened in order (``others`` are not part of it)."""
        return tuple(f for section in self.sections for f in section.fields)

    def field(self, path: Any) -> FormField | None:
        """The field for ``path`` (a term), looked up in the sections and then in ``others``; None when there is none."""
        path = to_engine(path)
        return next((f for f in (*self.fields, *self.others) if f.path == path), None)


# ---------------------------------------------------------------------------------------------------------------------
# reading the shapes


def _key(term: Any) -> tuple[str, str]:
    return (text(term), n3(term))


def _number(term: Any) -> float | None:
    try:
        return float(term.value)
    except (AttributeError, ValueError):
        return None


def _first_number(graph: Any, node: Any, predicate: Any) -> float | None:
    for value in sorted(graph.objects(node, predicate), key=_key):
        number = _number(value) if isinstance(value, Literal) else None
        if number is not None:
            return number
    return None


def _default_order(shapes: Any) -> float | None:
    """The ``shui:defaultOrder`` of the global configuration: the first numeric one, nodes in IRI text order (SHACL UI: the effective order)."""
    for _node, value in sorted(shapes.subject_objects(SHUI.defaultOrder), key=lambda pair: (_key(pair[0]), _key(pair[1]))):
        number = _number(value) if isinstance(value, Literal) else None
        if number is not None:
            return number
    return None


def _ints(shape: Any, predicate: Any) -> list[int]:
    found = []
    for value in shape.params.get(predicate, ()):
        try:
            found.append(int(value.value))
        except (AttributeError, ValueError):
            continue
    return found


def _constraints(shapes: Any, props: list[Any], plan: Plan) -> FieldConstraints:
    def terms(predicate: Any, what: str) -> tuple:
        found = {t for p in props for v in plan.shape(p).params.get(predicate, ()) for t in alternatives(shapes, v, what)}
        return ordered(found)

    def plain(predicate: Any) -> tuple:
        return ordered({v for p in props for v in plan.shape(p).params.get(predicate, ())})

    shape_of = [plan.shape(p) for p in props]
    mins = [n for s in shape_of for n in _ints(s, SH.minCount)]
    maxs = [n for s in shape_of for n in _ints(s, SH.maxCount)]
    min_len = [n for s in shape_of for n in _ints(s, SH.minLength)]
    max_len = [n for s in shape_of for n in _ints(s, SH.maxLength)]
    in_values: tuple | None = None
    for s in shape_of:
        for head in s.params.get(SH["in"], ()):
            members = rdf_list(shapes, head) if not isinstance(head, Literal) else None
            if members is None:
                continue
            in_values = tuple(members) if in_values is None else tuple(m for m in in_values if m in members)
    return FieldConstraints(
        datatypes=terms(SH.datatype, "sh:datatype"),
        classes=terms(SH["class"], "sh:class"),
        node_kinds=terms(SH.nodeKind, "sh:nodeKind"),
        min_count=max(mins) if mins else None,
        max_count=min(maxs) if maxs else None,
        min_length=max(min_len) if min_len else None,
        max_length=min(max_len) if max_len else None,
        patterns=tuple(sorted({v.value for s in shape_of for v in s.params.get(SH.pattern, ()) if isinstance(v, Literal)})),
        min_inclusive=plain(SH.minInclusive),
        max_inclusive=plain(SH.maxInclusive),
        min_exclusive=plain(SH.minExclusive),
        max_exclusive=plain(SH.maxExclusive),
        in_values=in_values,
    )


def _is_true(term: Any) -> bool:
    return isinstance(term, Literal) and term.value in ("true", "1")


def _simple_predicate(path: Any) -> tuple[Any, bool] | None:
    """``(predicate, inverse)`` for a predicate or an inverse predicate, else None (a complex path)."""
    if path.kind == "pred":
        return path.iri, False
    if path.kind == "inverse" and path.args[0].kind == "pred":
        return path.args[0].iri, True
    return None


class _Builder:
    def __init__(self, shapes: Any, data: Any, node: Any, *, role: str, subclass_of_in_shapes_graph: bool, inferred: Any, floor: Any) -> None:
        self.shapes, self.data, self.node, self.role = shapes, data, node, role
        self.inferred = inferred
        self.plan = Plan(shapes_graph=shapes)
        self.ctx = Context(data=data, plan=self.plan, subclass_of_in_shapes_graph=subclass_of_in_shapes_graph)
        self.check_context = _CheckContext(data, shapes, node, subclass_of_in_shapes_graph, floor)
        self.default_order = _default_order(shapes)
        self.notes: list[str] = []

    # ---- which shapes and property shapes apply

    def types_of(self, term: Any) -> set:
        found = set(self.data.objects(term, RDF.type))
        if self.inferred is not None:
            found |= set(self.inferred.objects(term, RDF.type))
        return found

    def holds(self, prop: Any) -> bool:
        """``stsh:formHeldBy`` / ``stsh:formOnlyFor`` of a property shape (the ``shacl_shacl_ui`` form shapes). ``formHeldBy``: the field is
        for a node that is a value of ``sh:parameter`` of a node of one of these classes, and for a node nothing holds yet. ``formOnlyFor``:
        the field is for a node of one of these classes. Types are the ``rdf:type`` triples of the data graph and ``inferred_graph``, with
        no subclass reasoning: pass the types a rule set infers (``infer_types``) in ``inferred_graph`` for a node that does not state its type."""
        held_by = list(self.shapes.objects(prop, STSH.formHeldBy))
        if held_by:
            graphs = [self.data] + ([self.inferred] if self.inferred is not None else [])
            holders = {h for g in graphs for h in g.subjects(SH.parameter, self.node) if not isinstance(h, Literal)}
            if holders and not any(kind in self.types_of(h) for h in holders for kind in held_by):
                return False
        only_for = list(self.shapes.objects(prop, STSH.formOnlyFor))
        return not only_for or any(kind in self.types_of(self.node) for kind in only_for)

    def contributions(self, node_shapes: tuple) -> dict[Any, list[Any]]:
        """``{path term: property shapes}``, the shapes of one path in the order of the module docstring, the paths in the order of
        their first shape."""
        props: list[Any] = []
        for node_shape in node_shapes:
            host = self.plan.shape(node_shape)
            for prop in dict.fromkeys(self.shapes.objects(node_shape, SH.property)):
                shape = self.plan.shape(prop)
                if shape.path is None or shape.deactivated or deactivated_at(self.ctx, shape, self.node) or _deactivated(host, SH.property, prop):
                    continue
                if prop not in props and self.holds(prop):
                    props.append(prop)
        props.sort(key=lambda p: (_first_number(self.shapes, p, SH.order) is None, _first_number(self.shapes, p, SH.order) or 0.0, _key(p)))
        by_path: dict[Any, list[Any]] = {}
        for prop in props:
            by_path.setdefault(self.plan.shape(prop).path.node, []).append(prop)
        return by_path

    # ---- what the first contributing shape says

    def literals(self, props: list[Any], predicate: Any) -> tuple:
        for prop in props:
            found = [o for o in self.shapes.objects(prop, predicate) if isinstance(o, Literal)]
            if found:
                return ordered(found)
        return ()

    def first_term(self, props: list[Any], predicate: Any) -> Any | None:
        for prop in props:
            found = sorted((o for o in self.shapes.objects(prop, predicate) if not isinstance(o, Literal)), key=_key)
            if found:
                return found[0]
        return None

    def order_of(self, props: list[Any]) -> float | None:
        for prop in props:
            number = _first_number(self.shapes, prop, SH.order)
            if number is not None:
                return number
        return self.default_order

    def group_info(self, group: Any) -> tuple[tuple, float | None]:
        label = self.literals([group], SH.name) or self.literals([group], RDFS.label)
        order = _first_number(self.shapes, group, SH.order)
        return label, self.default_order if order is None else order

    def suggested(self, props: list[Any]) -> tuple:
        for prop in props:
            heads = sorted(self.shapes.objects(prop, SHUI.suggestedValues), key=_key)
            for head in heads:
                members = rdf_list(self.shapes, head) if not isinstance(head, Literal) else None
                return tuple(members or ())
        return ()

    # ---- values

    def read(self, graph: Any, path: Any) -> set:
        return set(eval_path(graph, path, self.node)) if graph is not None else set()

    def read_predicate(self, graph: Any, predicate: Any) -> set:
        return set(graph.objects(self.node, predicate)) if graph is not None else set()

    def members(self, form: str, term: Any) -> tuple | None:
        if form == "single" or isinstance(term, Literal):
            return None
        for graph in (self.data, self.inferred):
            if graph is not None:
                found = rdf_list(graph, term)
                if found is not None:
                    return tuple(found)
        return None

    def values(self, path: Any, form: str, editable: bool, stored: set, computed: set, default: set, inferred: set, *, no_shape: bool = False) -> tuple[FormValue, ...]:
        simple = _simple_predicate(path) is not None if path is not None else True

        def build(term: Any, source: str) -> FormValue:
            if self.role == "viewer":
                reason: str | None = "role"
            elif not simple:
                reason = "path"
            elif source == "stored":
                reason = "no shape" if no_shape else None
            else:
                reason = source
            return FormValue(term, source, source == "stored" and editable and reason is None, reason, self.members(form, term))

        rows = [(ordered(stored), "stored"), (ordered(inferred - stored - computed - default), "inferred"), (ordered(computed), "computed"), (ordered(default), "default")]
        return tuple(build(term, source) for terms, source in rows for term in terms)

    def computed_values(self, fields: dict[Any, list[Any]], stored_of: dict) -> tuple[dict, dict]:
        """``{path: computed values}`` and ``{path: default values}``, from ONE ``evaluate()`` call for the node over the whole form.

        ``evaluate`` cannot be limited to one focus node cheaply: it resolves the targets of the property shapes it is asked about over
        the whole data graph and only then keeps the node, so it runs once, only for the predicates of the form's fields that have a
        property shape with ``sh:values`` or ``sh:defaultValue``, and not at all when there is none. The result holds the union of the
        stored values, ``sh:values`` outputs and (only when both are empty) ``sh:defaultValue`` outputs; what is not stored is computed,
        or a default when the field has no stored value and ``sh:values`` gave nothing. The data graph is not entailed for it."""
        wanted = {}
        for path, props in fields.items():
            simple = _simple_predicate(self.plan.shape(props[0]).path)
            has_values = any(self.plan.shape(p).values for p in props)
            has_default = any(self.plan.shape(p).default_values for p in props)
            if not (has_values or has_default):
                continue
            if simple is None or simple[1]:
                self.notes.append("sh:values and sh:defaultValue need a predicate as the path: no computed value for the field of " + text(path))
                continue
            wanted[path] = (simple[0], has_values, has_default, props)
        if not wanted:
            return {}, {}
        from starlayer.shacl.engine.evaluate import evaluate as engine_evaluate

        result = engine_evaluate(self.data, self.shapes, None, focus_nodes=[self.node], properties={v[0] for v in wanted.values()}, plan=self.plan)
        computed, default = {}, {}
        for path, (predicate, has_values, has_default, props) in wanted.items():
            new = set(result.objects(self.node, predicate)) - stored_of[path]
            if not new:
                continue
            if stored_of[path] or not has_default:
                computed[path] = new
            elif not has_values:
                default[path] = new
            else:
                from_values = self.expression_values(props) & new
                computed[path], default[path] = from_values, new - from_values
        return computed, default

    def expression_values(self, props: list[Any]) -> set:
        from starlayer.shacl.engine import expressions
        from starlayer.shacl.engine.plan import ExecutionError, only_kind

        found: set = set()
        for prop in props:
            for expr in self.plan.shape(prop).values:
                try:
                    found |= set(expressions.evaluate_expression(self.ctx, expr, self.node, {}))
                except ExecutionError as error:
                    only_kind(error, "expression")
                    continue
        return found


def _results(report: Any) -> tuple[ReportResult, ...]:
    if report is None:
        return ()
    if hasattr(report, "results") and hasattr(report, "report_graph"):
        return tuple(report.results)
    return report_results(getattr(report, "report_graph", report))


def form_model(
    shapes_graph: Any,
    data_graph: Any,
    node: Any,
    *,
    role: str = "editor",
    shapes: Any | None = None,
    empty: str = "auto",
    suggestions: bool = False,
    only_valid: bool = False,
    report: Any | None = None,
    widgets: Mapping[Any, Any] | None = None,
    scoring_graph: Any | None = None,
    implemented: Any | None = None,
    inferred_graph: Any | None = None,
    placement: Callable[[FormField], Any] | None = None,
    subclass_of_in_shapes_graph: bool = False,
    conformance_disallows: Any = None,
    target_options: Mapping[str, Any] | None = None,
    ont_graph: Any | None = None,
) -> FormModel:
    """The model of the form of ``node``; the public call is ``starlayer.shacl.form_model`` (its docstring has the options)."""
    from starlayer.shacl import _adapter
    from starlayer.shacl.engine import api

    if role not in _ROLES:
        raise ValueError("role must be 'editor' or 'viewer', got " + repr(role))
    if empty not in _EMPTY:
        raise ValueError("empty must be 'auto', 'all' or 'none', got " + repr(empty))
    data, shapes_g, _ont = _adapter._normalise(data_graph, shapes_graph, None)
    data, shapes_g = engine_view(data, "data graph"), engine_view(shapes_g, "shapes graph")
    inferred = engine_view(inferred_graph, "inferred graph") if inferred_graph is not None else None
    node = to_engine(node)
    builder = _Builder(shapes_g, data, node, role=role, subclass_of_in_shapes_graph=subclass_of_in_shapes_graph, inferred=inferred, floor=conformance_disallows)
    plan = builder.plan

    # which node shapes: those that target the node, or exactly the ones asked for (a lens)
    if shapes is None:
        found = api.target_shapes(
            data, shapes_g, node, ont_graph=ont_graph, subclass_of_in_shapes_graph=subclass_of_in_shapes_graph, **(target_options or {})
        )
        used = tuple(sorted(found, key=_key))
    else:
        asked = (shapes,) if isinstance(shapes, (NamedNode, BlankNode)) else tuple(shapes)
        kept = []
        for shape_term in dict.fromkeys(to_engine(s) for s in asked):
            if not any(True for _ in shapes_g.triples((shape_term, None, None))):
                raise ValueError("shape " + text(shape_term) + " is not a node of the shapes graph")
            if plan.shape(shape_term).deactivated or deactivated_at(builder.ctx, plan.shape(shape_term), node):
                builder.notes.append("the shape " + text(shape_term) + " is deactivated and was left out")
                continue
            kept.append(shape_term)
        used = tuple(kept)

    contributing = builder.contributions(used)

    # widgets: once per node shape (select_widgets per shape), finished for this node only when a matcher reads data
    choices: dict = dict(widgets) if widgets is not None else {}
    if widgets is None:
        listed = {p for props in contributing.values() for p in props}
        hosts = [s for s in used if any(p in listed for p in shapes_g.objects(s, SH.property))]
        for host in hosts:
            choices.update(
                select_widgets(
                    shape_node=host, shapes_graph=shapes_g, scoring_graph=scoring_graph, role=role, per="shape", implemented=implemented
                )
            )

    def widget_of(props: list[Any]) -> Any | None:
        for prop in props:
            choice = choices.get(prop)
            if choice is None:
                continue
            if isinstance(choice, WidgetChoice):
                chosen = choice.resolve(node, data) if choice.needs_data else choice.widget_without_data
            else:
                chosen = to_engine(choice)
            if chosen is not None:
                return chosen
        return None

    # values of the fields
    stored_of = {path: builder.read(data, plan.shape(props[0]).path) for path, props in contributing.items()}
    computed_of, default_of = builder.computed_values(contributing, stored_of)

    results = _results(report)
    node_errors = tuple(r for r in results if r.focus == node and r.path is None)

    def errors_for(path: Any) -> tuple[ReportResult, ...]:
        return tuple(r for r in results if r.focus == node and r.path == path)

    fields: list[FormField] = []
    for path, props in contributing.items():
        shape = plan.shape(props[0])
        simple = _simple_predicate(shape.path) is not None
        form = _adapter_value_form(plan, props[0])
        constraints = _constraints(shapes_g, props, plan)
        group = builder.first_term(props, SH.group)
        group_order = builder.group_info(group)[1] if group is not None else None
        editable = role == "editor" and simple
        candidates = None
        if suggestions:
            candidates = _adapter.candidate_values(
                data_graph=data,
                shacl_graph=shapes_g,
                property_shape=props[0],
                focus=node,
                only_valid=only_valid and simple,
                subclass_of_in_shapes_graph=subclass_of_in_shapes_graph,
                conformance_disallows=conformance_disallows,
            )
        fields.append(
            FormField(
                path=path,
                property_shapes=tuple(props),
                name=builder.literals(props, SH.name),
                description=builder.literals(props, SH.description),
                order=builder.order_of(props),
                widget=widget_of(props),
                values=builder.values(
                    shape.path,
                    form,
                    editable,
                    stored_of[path],
                    computed_of.get(path, set()),
                    default_of.get(path, set()),
                    builder.read(inferred, shape.path),
                ),
                value_form=form,
                required=bool(constraints.min_count),
                max_count=constraints.max_count,
                editable=editable,
                candidates=candidates,
                suggested=builder.suggested(props),
                errors=errors_for(path),
                secondary=any(_is_true(o) for p in props for o in shapes_g.objects(p, STSH.secondary)),
                constraints=constraints,
                group=group,
                group_order=group_order,
                _context=builder.check_context,
            )
        )

    # empty fields
    def keep(f: FormField) -> bool:
        if f.values or empty == "all":
            return True
        if empty == "none" or role == "viewer":
            return False
        return f.required

    shown = [f for f in fields if keep(f)]
    hidden = len(fields) - len(shown)

    # order and sections
    def core_key(f: FormField) -> tuple:
        name = text(f.name[0]) if f.name else ""
        tail = (f.order is None, f.order or 0.0, name.casefold(), name, _key(f.path))
        if f.group is None:
            return (0, False, 0.0, "", "", *tail)
        label = builder.group_info(f.group)[0]
        label_text = text(label[0]) if label else ""
        return (1, f.group_order is None, f.group_order or 0.0, label_text.casefold(), text(f.group), *tail)

    ordering = (lambda f: (placement(f), core_key(f))) if placement is not None else core_key
    shown.sort(key=ordering)
    primary = [f for f in shown if not f.secondary]
    secondary = [f for f in shown if f.secondary]
    sections: list[FormSection] = []
    seen: dict[Any, list[FormField]] = {}
    for f in primary:
        seen.setdefault(f.group, []).append(f)
    for group, members in seen.items():
        label, order = builder.group_info(group) if group is not None else ((), None)
        sections.append(FormSection(group=group, label=label, order=order, fields=tuple(members)))
    if secondary:
        sections.append(FormSection(group=None, label=(), order=None, fields=tuple(secondary), collapsed=True))

    # predicates no used shape covers
    covered = {_simple_predicate(plan.shape(props[0]).path)[0] for props in contributing.values() if _simple_predicate(plan.shape(props[0]).path) and not _simple_predicate(plan.shape(props[0]).path)[1]}
    for node_shape in used:
        if any(_is_true(o) for o in shapes_g.objects(node_shape, SH.closed)):
            for head in shapes_g.objects(node_shape, SH.ignoredProperties):
                covered |= set(rdf_list(shapes_g, head) or ()) if not isinstance(head, Literal) else set()
    others = []
    for predicate in ordered(set(data.predicates(node)) - covered):
        stored = set(data.objects(node, predicate))
        others.append(
            FormField(
                path=predicate,
                property_shapes=(),
                name=(),
                description=(),
                order=None,
                widget=None,
                values=builder.values(None, "single", False, stored, set(), set(), builder.read_predicate(inferred, predicate), no_shape=True),
                value_form="single",
                required=False,
                max_count=None,
                editable=False,
                candidates=None,
                suggested=(),
                errors=errors_for(predicate),
                secondary=False,
                constraints=FieldConstraints(),
                _context=builder.check_context,
            )
        )
    return FormModel(
        node=node,
        role=role,
        shapes=used,
        sections=tuple(sections),
        others=tuple(others),
        notes=tuple(dict.fromkeys(builder.notes)),
        node_errors=node_errors,
        hidden_empty=hidden,
    )


def _adapter_value_form(plan: Plan, property_shape: Any) -> str:
    from starlayer.shacl.engine.value_form import value_form_in

    return value_form_in(plan, property_shape)
