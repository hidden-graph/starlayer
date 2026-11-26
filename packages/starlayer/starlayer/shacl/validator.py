"""The public SHACL API: ``validate``, ``validate_each``, ``apply_rules``, ``evaluate`` and ``StarShaclProcessor``.

Each call normalises its graphs and hands them to the native SHACL 1.2 engine (``starlayer.shacl.engine``) through
``starlayer.shacl._adapter``. ``StarShaclProcessor`` binds a shapes graph (and optionally an ontology, a data graph, a scoring
graph and an entailment regime) once and offers the same operations as methods.
"""

from __future__ import annotations

import sys
from collections.abc import Callable, Iterable
from typing import Any

import pyoxigraph as ox

from starlayer.errors import ExecutionError, only_kind
from starlayer.shacl import _adapter
from starlayer.shacl.candidates import Candidates
from starlayer.shacl.engine.terms import RDF, SH, BlankNode, n3
from starlayer.shacl.form_model import FormModel
from starlayer.shacl.normalization import normalize_to_starlayer_graph
from starlayer.shacl.results import RulesResult, ValidationReport
from starlayer.shacl.validation_modes import ValidationMode
from starlayer.shacl.value_check import ValueCheck


def validate(
    data_graph: Any,
    shacl_graph: Any | None = None,
    ont_graph: Any | None = None,
    *,
    mode: str | ValidationMode | None = None,
    shapes_graph_loader: Callable[[Any], Any | None] | None = None,
    ignore_imports: bool = False,
    meta_shapes_extra: Iterable[Any] = (),
    data_graph_iri: Any | None = None,
    shapes_graph_resource: Any | None = None,
    shapes_graph_iri: Any | None = None,
    specification_graph: Any | None = None,
    include_used_configuration: bool = False,
    **kwargs: Any,
) -> ValidationReport:
    """Validates ``data_graph`` against ``shacl_graph`` per SHACL 1.2 and returns a ``ValidationReport``.

    Args:
        data_graph: The RDF data to validate: a ``StarLayerGraph`` / ``StarLayerDataset`` (used as it is) or a
            ``pyoxigraph.Store``. It is never changed unless ``inplace=True``.
        shacl_graph: The shapes graph. ``None`` reads the shapes from ``data_graph`` itself.
        ont_graph: An optional ontology graph. Its axioms (``rdfs:domain``, ``rdfs:subClassOf`` ...) are visible to entailment, but
            its triples are never copied into ``data_graph``.
        mode: A named preset of options (``"validation"``, ``"rules"`` or ``"debug"``); any of its options can be overridden per
            call through ``**kwargs``.
        shapes_graph_loader: Resolves the ``owl:imports`` of the shapes graph and of ``ont_graph``. Every import must end up a subject of the
            graph, or the call raises ``ExecutionError`` kind ``"import"`` (``error.unresolved`` lists the IRIs): no loader, a loader that
            returns ``None`` or a graph without the IRI, and a loader that raises (wrapped, the exception as ``__cause__``) are all
            that error. An import of an ontology StarLayer has built in (a registered ``starontology`` ontology, ``sh:`` among them) needs
            no loader and is never passed to one. An ``owl:imports`` object that is not an IRI is a ``ShapeCompileError``.
        ignore_imports: Load nothing and check nothing: the shapes graph and ontology graph are used as they are.
        meta_shapes_extra: Extra graphs for the shapes-about-shapes check when ``meta_shacl=True``.
        data_graph_iri, shapes_graph_iri: Recorded as ``sh:usedDataGraph`` / ``sh:usedShapesGraph`` on the ``sh:ValidationActivity`` that generated the report; each defaults
            to the graph's own identifier when that is an IRI.
        shapes_graph_resource: Validate against a named ``sh:ShapesGraph`` module of ``shacl_graph`` (its IRI becomes
            ``sh:usedShapesGraph``), or, for an IRI that is not a module of it, only tag the report with that IRI.
        specification_graph: Lets Profiling derive ``dcterms:conformsTo`` from the derived ``sh:conformsToShapesGraph``.
        include_used_configuration: Also record the options in effect (``sh:usedConfiguration`` on that activity).
        **kwargs: Option overrides (a ``StarShaclProcessor``'s ``allow_warnings`` / ``allow_infos`` can also be bound at construction and
            are overridden by the same keyword here): ``inference`` (an entailment regime IRI such as ``ENTAILMENT.RDFS``, or an iterable of them),
            ``inplace``, ``meta_shacl``, ``rules`` (None: run rules when the shapes declare ``sh:entailment``; True: always; False: never; ``advanced`` is deprecated for it), ``allow_warnings``, ``allow_infos``,
            ``engine`` (``"hermit"``, the default, or ``"rustdl"``) and ``timeout`` (seconds, default 120) for the ``OWL-Direct`` regime
            (a ``ValueError`` for any other), ``recompute`` (``"onChange"``, the default, ``"never"``, ``"always"``: when the entailed copy
            of the data, which ``query(entailment=...)`` shares, is made again; see ``StarLayerGraph.query``),
            ``abort_on_first``, ``subclass_of_in_shapes_graph`` (default ``False``: SHACL 1.2 Core's
            optional parameter; ``True`` reads ``rdfs:subClassOf`` for ``sh:class``, ``sh:targetClass``, implicit class targets,
            ``sh:rootClass`` and ``shnex:instancesOf`` from the shapes graph as well as the data graph, ``rdf:type`` from the data graph
            only). An unknown option is a ``TypeError``.

    Returns:
        A ``ValidationReport``: ``conforms``, ``report_graph`` (an ``StarLayerGraph``) and ``report_text``, ``data_graph`` (the caller's graph when
        ``inplace=True``, else ``None``) and ``diagnostics``.
    """
    return _adapter.validate(
        data_graph=data_graph,
        shacl_graph=shacl_graph,
        ont_graph=ont_graph,
        inference=kwargs.get("inference"),
        mode=mode,
        options=kwargs,
        shapes_graph_loader=shapes_graph_loader,
        ignore_imports=ignore_imports,
        meta_shapes_extra=meta_shapes_extra,
        data_graph_iri=data_graph_iri,
        shapes_graph_iri=shapes_graph_iri,
        shapes_graph_resource=shapes_graph_resource,
        specification_graph=specification_graph,
        include_used_configuration=include_used_configuration,
    )


def _each_items(dataset: Any) -> list[tuple[Any, Any]]:
    """The ``(key, graph)`` pairs ``validate_each`` validates: the dataset's graphs, ``None`` for a default graph that holds triples,
    then the named graphs by name. Only a dataset (a ``pyoxigraph.Store`` is wrapped as one) is taken: a list or mapping of graphs
    has no one place to say what the graphs are called, so it is a ``TypeError`` that shows how to build the dataset."""
    from starlayer.graph import StarLayerDataset
    from starlayer.graph.inputs import as_oxigraph

    if not isinstance(dataset, StarLayerDataset):
        if isinstance(dataset, ox.Store):
            dataset = StarLayerDataset(store=dataset)
        else:
            rdflib = sys.modules.get("rdflib")
            if rdflib is not None and isinstance(dataset, rdflib.Graph):
                as_oxigraph(dataset, "dataset of validate_each()")  # raises the TypeError that names from_rdflib
            raise TypeError(
                f"validate_each() takes a dataset (a StarLayerDataset or pyoxigraph Store), not {type(dataset).__name__}: "
                "validate a single graph with validate(graph, shacl_graph); to validate several graphs one by one, add them to "
                "a StarLayerDataset, one graph per name, for example ds = StarLayerDataset(); ds.graph('urn:g:1').extend(graph_1) "
                "(from a mapping: for name, g in graphs.items(): ds.graph(name).extend(g)), then validate_each(ds, shacl_graph)"
            )
    default = dataset.default_graph
    return ([(None, default)] if len(default) else []) + [
        (name, dataset.graph(name)) for name in sorted(dataset.graph_names(), key=str)
    ]


def validate_each(
    dataset: Any,
    shacl_graph: Any | None = None,
    ont_graph: Any | None = None,
    **kwargs: Any,
) -> dict[Any, ValidationReport]:
    """Validates each graph of ``dataset`` on its own against the same ``shacl_graph`` / ``ont_graph``; the shapes are parsed once
    for the whole batch. ``kwargs`` are those of :func:`validate`.

    The result is keyed by graph name, plus ``None`` for the default graph when it holds any triples. Only a ``StarLayerDataset``
    (or a ``pyoxigraph.Store``) is taken, so every graph has a name to be reported under; validating the dataset *as a whole* is
    :func:`validate`, which sees the union of its graphs."""
    items = _each_items(dataset)
    with _adapter.shared_plans():
        return {key: validate(data_graph, shacl_graph, ont_graph, **kwargs) for key, data_graph in items}


def evaluate(
    data_graph: Any,
    shacl_graph: Any | None = None,
    ont_graph: Any | None = None,
    *,
    inference: Any | None = None,
    engine: str = "hermit",
    timeout: Any | None = None,
    recompute: str = "onChange",
    focus_nodes: Any | None = None,
    properties: Any | None = None,
    rules_entailment: bool = False,
    validate: bool = False,
) -> Any:
    """Computes the ``sh:values`` / ``sh:defaultValue`` virtual properties of ``shacl_graph`` and returns a shape-driven subgraph.

    The returned graph holds, for each property shape with a simple ``sh:path``, its stored values for the shape's own focus nodes
    with the computed values unioned in (``sh:defaultValue`` only when there is no stored value), never the whole of
    ``data_graph``. ``data_graph`` is not changed, and the result is not meant to be persisted: virtual values are computed on
    demand.

    Args:
        data_graph: The RDF data to evaluate over.
        shacl_graph: The shapes graph; ``None`` reads the shapes from ``data_graph``.
        ont_graph: An optional ontology graph, visible to entailment only.
        inference: An entailment regime IRI (or an iterable of them), applied together with the shapes graph's own
            ``sh:entailment`` before evaluating.
        engine, timeout, recompute: As for :func:`validate` (``OWL-Direct`` engine and timeout; when the shared entailed copy is made again).
        focus_nodes: Restrict evaluation to these focus nodes (``None``: every node the shapes target).
        properties: Restrict evaluation to property shapes with one of these ``sh:path`` IRIs (``None``: all).
        rules_entailment: Also run the rules the shapes graph names in ``sh:entailment`` first.
        validate: Make the evaluation conformance-gated, like ``extract_subgraph()``: the values for a focus node are computed only
            when the node conforms to the shape that targets it, checked as ``validate()`` does (computed ``sh:values`` values
            included; a deactivated shape is skipped). A node that does not conform contributes nothing; a node several shapes
            target contributes the values of the shapes it conforms to, a value computed twice once. Off by default: evaluation
            is then a lens that needs no conformance and costs no validation. To see why a node was left out, run ``validate()``;
            its report is the explanation.
    """
    return _adapter.evaluate(
        data_graph,
        shacl_graph,
        ont_graph,
        inference=inference,
        engine=engine,
        timeout=timeout,
        recompute=recompute,
        focus_nodes=focus_nodes,
        properties=properties,
        rules_entailment=rules_entailment,
        validate=validate,
    )


def apply_rules(
    data_graph: Any,
    shacl_graph: Any | None = None,
    ont_graph: Any | None = None,
    include_source_rule_provenance: bool = False,
    rule_set: Any | None = None,
    **kwargs: Any,
) -> RulesResult:
    """Executes the SHACL rules of ``shacl_graph`` over ``data_graph`` until nothing new is inferred, and returns what they inferred.

    The rules run on an overlay over the data, so a rule sees what another inferred and ``data_graph`` is not copied or changed.
    Nothing is validated: to check the outcome, call ``validate(data_graph, shacl_graph, rules=True)`` (the rules, then a
    validation of the data with what they inferred, against the same shapes), or validate the data together with
    ``result.inferred_graph`` against any shapes you choose (they need not be the shapes that hold the rules).

    Covers ``sh:TripleRule`` and ``sh:SPARQLRule`` (shape-attached, in rule sets, or global) and ``sh:sourceRule`` provenance.

    Args:
        data_graph: The data the rules run over: an Oxigraph-backed graph.
        shacl_graph: The shapes graph holding the rules; ``None`` reads them from ``data_graph``.
        ont_graph: An optional ontology graph, visible to entailment only.
        include_source_rule_provenance: Record, for every inferred triple, a reifier ``_:r rdf:reifies <<( s p o )>>`` with
            ``_:r sh:sourceRule <rule>`` (Inference Rules section 9).
        rule_set: Run only the rules of this ``sh:RuleSet`` (an IRI, or an iterable of IRIs).
        **kwargs: Only the options of :func:`validate` that rule execution uses: ``inference`` (an entailment regime for the rules
            to match over, together with the shapes graph's own ``sh:entailment``), ``engine``, ``timeout``, ``recompute``,
            ``subclass_of_in_shapes_graph`` (also for the rules' class targets), ``meta_shacl`` and the named ``meta_shapes_extra``,
            ``ignore_imports``, ``shapes_graph_loader`` (how the shapes graph is read and checked), and the rule limits
            ``max_iterations`` (default 1000: more iterations than that without reaching a fixpoint raise an ``ExecutionError`` of kind ``"limit"``)
            and ``max_triples`` (default 5,000,000: more inferred triples than that raise an ``ExecutionError`` of kind ``"limit"``;
            an inferred triple costs about 1.3-1.9 KB, so a million is about 1.3 GB; ``None`` removes the cap; a non-int or negative value is refused).
            An option that only describes a validation (``allow_warnings``, ``allow_infos``, ``abort_on_first``,
            ``include_used_configuration``, ``rules``, ...) is a ``TypeError`` naming ``validate()``.
            On a ``StarShaclProcessor`` the constructor's values of the options above are the defaults, and a keyword here
            overrides them; its validation defaults are not applied.

    Returns:
        A ``RulesResult``: ``inferred_graph`` holds only the triples the rules produced (and the ``sh:sourceRule`` reifiers).
    """
    return _adapter.apply_rules(
        data_graph=data_graph,
        shacl_graph=shacl_graph,
        ont_graph=ont_graph,
        include_source_rule_provenance=include_source_rule_provenance,
        rule_set=rule_set,
        options=kwargs,
    )


def target_nodes(
    *,
    data_graph: Any,
    shacl_graph: Any | None = None,
    shape_node: Any,
    ont_graph: Any | None = None,
    inference: Any | None = None,
    engine: str = "hermit",
    timeout: Any | None = None,
    recompute: str = "onChange",
    subclass_of_in_shapes_graph: bool = False,
) -> tuple[Any, ...]:
    """The nodes ``shape_node`` targets in ``data_graph``, in declaration order and without duplicates: the nodes ``validate()``
    reports on for that shape (``sh:targetNode``, including a node expression, ``sh:targetClass`` with subclasses,
    ``sh:targetSubjectsOf``, ``sh:targetObjectsOf``, ``sh:targetWhere``, data-graph ``sh:shape`` and implicit class targets).

    ``shacl_graph=None`` reads the shapes from ``data_graph``. The shapes graph's own ``sh:entailment`` and ``inference`` (an
    entailment regime IRI or an iterable of them) are applied first, over the data graph and ``ont_graph``, without changing
    either. ``engine``, ``timeout`` and ``recompute`` are as for :func:`validate`. ``subclass_of_in_shapes_graph=True`` reads the ``rdfs:subClassOf`` triples of ``sh:targetClass`` and implicit class
    targets from the shapes graph too, as the option of that name does in :func:`validate`."""
    return _adapter.target_nodes(
        data_graph=data_graph,
        shacl_graph=shacl_graph,
        shape_node=shape_node,
        ont_graph=ont_graph,
        inference=inference,
        engine=engine,
        timeout=timeout,
        recompute=recompute,
        subclass_of_in_shapes_graph=subclass_of_in_shapes_graph,
    )


def target_shapes(
    *,
    data_graph: Any,
    shacl_graph: Any | None = None,
    node: Any,
    ont_graph: Any | None = None,
    inference: Any | None = None,
    engine: str = "hermit",
    timeout: Any | None = None,
    recompute: str = "onChange",
    subclass_of_in_shapes_graph: bool = False,
) -> tuple[Any, ...]:
    """The shapes that target ``node`` in ``data_graph``: the shapes ``validate()`` checks it against, so the reverse of
    :func:`target_nodes` (``node in target_nodes(shape_node=s)`` exactly when ``s in target_shapes(node=node)``). A deactivated shape is not
    included. ``shacl_graph=None`` reads the shapes from ``data_graph``, and the other options are those of :func:`target_nodes`. A
    form-building application uses this to pick the shapes of a node."""
    return _adapter.target_shapes(
        data_graph=data_graph,
        shacl_graph=shacl_graph,
        node=node,
        ont_graph=ont_graph,
        inference=inference,
        engine=engine,
        timeout=timeout,
        recompute=recompute,
        subclass_of_in_shapes_graph=subclass_of_in_shapes_graph,
    )


def candidate_values(
    shapes_graph: Any,
    property_shape: Any,
    data_graph: Any,
    *,
    focus: Any | None = None,
    only_valid: bool = False,
    subclass_of_in_shapes_graph: bool = False,
) -> Candidates:
    """What a form can offer for the field of ``property_shape``: the values its constraints name (``sh:in``, ``sh:hasValue``) or the
    nodes of its ``sh:class`` / ``sh:rootClass``, subclasses included, as a ``Candidates``. Constraints that name values intersect;
    ``sh:or`` unites its alternatives; ``subclass_of_in_shapes_graph`` is as for :func:`validate`.

    With ``only_valid=True`` (it needs ``focus``) each candidate is tried as the only value of the property of ``focus``, on a
    scratch copy of the data, and kept when ``property_shape`` then conforms; the property's path must be a predicate or an inverse
    predicate. A ``ValueError`` for a ``property_shape`` that is not a property shape of ``shapes_graph``."""
    return _adapter.candidate_values(
        data_graph=data_graph,
        shacl_graph=shapes_graph,
        property_shape=property_shape,
        focus=focus,
        only_valid=only_valid,
        subclass_of_in_shapes_graph=subclass_of_in_shapes_graph,
    )


def value_form(shapes_graph: Any, property_shape: Any) -> str:
    """How the value of the field of ``property_shape`` is held: ``"single"`` (one term), ``"list"`` (the value must be an RDF list) or
    ``"single-or-list"`` (the shape allows either), read from the shape's own constraints: ``sh:node`` / ``sh:and`` to a shape that
    describes a list (``shsh:ListShape``, ``sh:class rdf:List``, the SHACL 1.2 list constraints), ``sh:or`` / ``sh:xone`` with both kinds
    of alternative. A ``ValueError`` for a ``property_shape`` that is not a property shape of ``shapes_graph``."""
    return _adapter.value_form(shacl_graph=shapes_graph, property_shape=property_shape)


def check_value(
    shapes_graph: Any,
    property_shape: Any,
    focus: Any,
    value: Any,
    data_graph: Any,
    *,
    subclass_of_in_shapes_graph: bool = False,
) -> ValueCheck:
    """Whether ``value`` would be accepted for the field of ``property_shape`` of ``focus``, as a ``ValueCheck``.

    On a scratch copy of ``data_graph`` ``value`` replaces the current values of the property of ``focus``, and ``focus`` is validated
    against ``property_shape`` only (as ``candidate_values(only_valid=True)`` does); ``data_graph`` is not changed. ``value`` is one
    pyoxigraph term (a list is a term the caller built). The property's path must be a predicate or an inverse predicate, else a
    ``ValueError``; so it is for a ``property_shape`` that is not a property shape of ``shapes_graph``."""
    return _adapter.check_value(
        data_graph=data_graph,
        shacl_graph=shapes_graph,
        property_shape=property_shape,
        focus=focus,
        value=value,
        subclass_of_in_shapes_graph=subclass_of_in_shapes_graph,
    )


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
    widgets: Any | None = None,
    scoring_graph: Any | None = None,
    implemented: Any | None = None,
    inferred_graph: Any | None = None,
    placement: Any | None = None,
    subclass_of_in_shapes_graph: bool = False,
) -> FormModel:
    """The form of ``node``: its fields with widgets, values and where each value comes from, as a ``FormModel``.

    A join of answers StarLayer already gives, with no vocabulary of its own. The data graph may suggest (stored values, candidates)
    but never decides validity: ``errors`` come only from a ``report`` you pass (a ``ValidationReport`` or a report graph), and nothing
    is validated here; ``FormField.check(value)`` validates one value on demand.

    ``role``: ``"editor"`` or ``"viewer"`` (SHACL UI). ``shapes=None``: the node shapes that target ``node`` (``target_shapes``),
    merged by ``sh:path`` into one field each, every contributing property shape kept; ``shapes=[S, ...]`` (terms) uses exactly those
    node shapes, whether they target the node or not. A deactivated shape is ignored. ``empty``: ``"auto"`` (a viewer hides fields with
    no value; an editor keeps required fields and fields with a value), ``"all"`` or ``"none"``; ``hidden_empty`` counts what is left out.
    ``suggestions=True`` fills ``FormField.candidates`` with ``candidate_values(focus=node, only_valid=only_valid)`` (never by default: it
    costs); ``shui:suggestedValues`` are always in ``suggested``.

    ``widgets`` is an optional precomputed ``{property shape: WidgetChoice | widget IRI | None}`` for ``role``, what
    ``select_widgets(per="shape")`` returns (a ``WidgetChoice`` is finished for ``node`` when it needs data); a property shape it does not
    hold has no widget. Without it ``select_widgets`` runs per node shape with ``scoring_graph`` (``None``: no scoring catalog, as for
    ``select_widgets``, so only widgets the shapes name) and ``implemented`` (the widget IRIs the app can draw). ``inferred_graph`` is a graph
    of derived triples (``RulesResult.inferred_graph``): a value found only there has source ``"inferred"``; stored values come from
    ``data_graph`` alone. ``placement`` is a callable ``field -> sort key`` that replaces the Core ordering of fields within a section
    and of the sections (the section of the first field in key order comes first); the default is the Core rule: ungrouped fields first
    by their ``sh:order``, then groups by the group's ``sh:order`` (``shui:defaultOrder`` when it has none, then last), then fields by
    their own order, ties by ``sh:name`` text then IRI text.

    ``sh:values`` and ``sh:defaultValue`` values come from one ``evaluate()`` call for the whole form, which cannot be limited to one
    focus node cheaply (it resolves the property shapes' targets over the whole data graph), so it runs only when a field's shape has
    one; a shape lens (``shapes=``) that does not target ``node`` gets none. ``stsh:formHeldBy`` / ``stsh:formOnlyFor`` on a property
    shape are applied (see ``FormField`` and ``FormModel`` for the rest). rdflib graphs or terms are a ``TypeError`` naming
    ``StarLayerGraph.from_rdflib``."""
    return _adapter.form_model(
        shapes_graph=shapes_graph,
        data_graph=data_graph,
        node=node,
        role=role,
        shapes=shapes,
        empty=empty,
        suggestions=suggestions,
        only_valid=only_valid,
        report=report,
        widgets=widgets,
        scoring_graph=scoring_graph,
        implemented=implemented,
        inferred_graph=inferred_graph,
        placement=placement,
        subclass_of_in_shapes_graph=subclass_of_in_shapes_graph,
    )


def _drop_nonmember_property_shape_refs(module_graph: Any) -> Any:
    """Remove ``sh:property`` links from an extracted shapes-graph module to a named property shape that is not itself a member.

    ``extract_shapes_graph()`` deliberately leaves such a reference dangling (the module is exactly its members), and a property
    shape without ``sh:path`` is an ill-formed shapes graph. A non-member's constraints are not part of the module, so the link is
    dropped for validation only (GitHub issue #94)."""
    for s, o in list(module_graph.subject_objects(SH.property)):
        if not isinstance(o, BlankNode) and not any(True for _ in module_graph.triples((o, SH.path, None))):
            module_graph.remove((s, SH.property, o))
    return module_graph


def _find_genuine_report_node(report_graph: Any) -> Any | None:
    """The top-level ``sh:ValidationReport`` node of ``report_graph``, told apart from any incidental ``sh:ValidationReport``-typed
    node copied in as some result's ``sh:value`` / ``sh:focusNode`` (a data file can carry its own expected-result report).

    The genuine report is a fresh node that nothing in the graph refers to;
    among several candidates the one with the most ``sh:result`` wins, ties broken by identifier, so the answer never depends on
    iteration order. ``None`` when there is no report node at all."""
    candidates = sorted({s for s, _, _ in report_graph.triples((None, RDF.type, SH.ValidationReport))}, key=n3)  # str-ok: a tie-break
    if len(candidates) <= 1:
        return candidates[0] if candidates else None

    def only_linked_to(node: Any) -> bool:
        return not any(True for _ in report_graph.triples((None, None, node)))

    roots = [n for n in candidates if only_linked_to(n)]
    if len(roots) == 1:
        return roots[0]
    pool = roots or candidates
    return max(pool, key=lambda n: (len(list(report_graph.objects(n, SH.result))), n3(n)))


class _Unset:
    """The type of ``_UNSET``: "not given", for a parameter where ``None`` is a real value."""

    def __repr__(self) -> str:
        return "<not set>"


# "Not set" where ``None`` means something: ``shapes_graph_loader=None`` on a call means no loader, ``inference=None`` no regime.
# A call that says ``None`` must be able to beat a constructor value.
_UNSET: Any = _Unset()

# What a StarShaclProcessor can bind at construction, as defaults of the calls that use them (stored as same-named attributes;
# ``None`` = not set). Three groups, by where they apply:
# - validation options (``validate()`` and the other calls that check or target against the shapes): keys of the call's ``**kwargs``;
# - the named parameters of ``validate()`` and ``apply_rules()`` that say how the shapes graph is read;
# - the limit of rule execution (``apply_rules()`` only).
# ``apply_rules()`` takes the ``_RULES_DEFAULTS`` among them: the options that only describe a validation stay out.
# Precedence, lowest first: built-in default, constructor, ``mode=`` preset, keyword on the call.
_VALIDATION_DEFAULTS = (
    "allow_warnings",
    "allow_infos",
    "meta_shacl",
    "subclass_of_in_shapes_graph",
    "engine",
    "timeout",
    "recompute",
)
_SHAPES_GRAPH_DEFAULTS = ("meta_shapes_extra", "ignore_imports", "shapes_graph_loader")
_RULE_LIMIT_DEFAULTS = ("max_iterations", "max_triples")
_NONE_IS_A_VALUE = frozenset({"max_triples"})  # constructor options where None is a real value (no cap), unset is _UNSET
_RULES_DEFAULTS = (
    "meta_shacl",
    "subclass_of_in_shapes_graph",
    "engine",
    "timeout",
    "recompute",
    *_SHAPES_GRAPH_DEFAULTS,
    *_RULE_LIMIT_DEFAULTS,
)
_CONSTRUCTOR_OPTIONS = _VALIDATION_DEFAULTS + _SHAPES_GRAPH_DEFAULTS + _RULE_LIMIT_DEFAULTS


class StarShaclProcessor:
    """A shapes graph (and optionally an ontology graph, a default data graph, a scoring graph and an entailment regime), bound once,
    to validate, run rules against, or evaluate node expressions over any number of data graphs.

    Construct one per shapes set (``person_processor = StarShaclProcessor(person_shapes)``), then call ``validate`` / ``apply_rules`` /
    ``evaluate`` with whatever data graph you are checking. ``select_widgets`` needs no data graph: it chooses SHACL 1.2 UI widgets
    from the shapes graph alone. Shape-driven subgraph extraction is the plain function ``starlayer.shacl.extract_subgraph()``.

    ``inference`` is an entailment regime IRI (``ENTAILMENT.RDFS``) or an iterable of them, the default regime of every call. It is
    applied to the data graph together with the shapes graph's own ``sh:entailment``. ``validate()``, ``validate_each()``,
    ``apply_rules()``, ``evaluate()`` and ``target_nodes()`` take ``inference=`` too: a value given on a call REPLACES the constructor's regime(s)
    for that call only (they are not merged); ``inference=None`` or an empty iterable means no regime of the call's own, and not
    giving it means the constructor's. The shapes graph's own ``sh:entailment`` applies in every case (SHACL 1.2 Core), on top of
    whatever regime the call or the constructor selects. The entailed copy of the data is kept per store and per set of regimes (shared with ``query(entailment=...)`` for the OWL
    regimes; SPARQL's RDF and RDFS are a query rewrite, SHACL's a copy), so a call with RDFS and a call with OWL-RDF-Based on the
    same data each compute their closure once and both stay cached until the data is written to (``recompute=`` as for ``query()``).

    **A bad shapes graph is refused when the processor is built.** With a ``shacl_graph``, the constructor reads and compiles the
    shapes (every ``ShapeError`` that reading them can raise, constraint parameters included) and, with ``meta_shacl=True``, runs the
    meta-SHACL check (``MetaShaclError``); ``validate()`` reuses the compiled plan and the check's result. See ``__init__`` for what
    is still found only at evaluation time, for ``owl:imports``, and for a shapes graph that changes afterwards. A processor with no
    shapes graph is not checked. This applies to every use of the processor (``evaluate()``, ``apply_rules()`` and
    ``select_widgets()`` included); the module-level ``validate()`` and ``apply_rules()`` still check per call.

    The options that describe the shapes graph, or are safety limits, are usually the same on every call, so they can be bound at
    construction as defaults (``_CONSTRUCTOR_OPTIONS``); a call passing the same keyword overrides them, including with the value
    that looks like the built-in default (``ignore_imports=False`` beats a constructor ``True``). Precedence, lowest first: built-in
    default, constructor, ``mode=`` preset, call keyword. A preset names only what it changes, so it never undoes a constructor
    value.

    - ``allow_warnings``, ``allow_infos``: ``validate()`` only (``apply_rules()`` validates nothing and
      refuses them). ``meta_shacl``, ``subclass_of_in_shapes_graph``, ``engine``, ``timeout``, ``recompute``: ``validate()`` and
      ``apply_rules()``. ``subclass_of_in_shapes_graph=True`` (built-in: ``False``) is the SHACL 1.2 Core parameter of that name:
      ``rdfs:subClassOf`` triples for ``sh:class``, ``sh:targetClass``, implicit class targets and ``sh:rootClass`` are read from
      the shapes graph as well as the data graph (``rdf:type`` from the data graph only).
    - ``meta_shapes_extra``, ``ignore_imports``, ``shapes_graph_loader``: how the shapes graph is read, for ``validate()`` and
      ``apply_rules()``. On a call, ``shapes_graph_loader=None`` drops a constructor loader.
    - ``max_iterations``: ``apply_rules()`` only (built-in: 1000).
    - ``max_triples``: ``apply_rules()`` only (built-in: 5,000,000 inferred triples; ``None`` removes the cap).

    ``target_nodes()`` takes ``subclass_of_in_shapes_graph`` (its default is the constructor's value, a keyword overrides it), since
    it answers what ``validate()`` targets; ``evaluate()``, ``select_widgets()``, ``close_shape()`` and ``extract_shapes_graph()``
    use none of them: they never took these options. An unset ``None`` default is the unbound state; where ``None`` is a real value the parameter's
    default shows as ``<not set>`` (a call's ``shapes_graph_loader`` and ``inference``).
    """

    def __init__(
        self,
        shacl_graph: Any | None = None,
        ont_graph: Any | None = None,
        *,
        data_graph: Any | None = None,
        scoring_graph: Any | None = None,
        inference: Any | None = None,
        allow_warnings: bool | None = None,
        allow_infos: bool | None = None,
        meta_shacl: bool | None = None,
        meta_shapes_extra: Iterable[Any] | None = None,
        ignore_imports: bool | None = None,
        shapes_graph_loader: Callable[[Any], Any | None] | None = None,
        max_iterations: int | None = None,
        max_triples: int | None = _UNSET,  # type: ignore[assignment]
        subclass_of_in_shapes_graph: bool | None = None,
        engine: str | None = None,
        timeout: float | None = None,
        recompute: str | None = None,
    ) -> None:
        """Bind the shapes, ontology, default data and scoring graphs for validation.

        The keyword-only options after ``inference`` are defaults of the calls that use them (see the class docstring for which);
        a call's own keyword overrides them. ``None`` means not set (the built-in default applies).
        ``subclass_of_in_shapes_graph`` (``None``: built-in ``False``) makes ``validate()`` and ``apply_rules()`` read
        ``rdfs:subClassOf`` from the shapes graph too, as in :func:`validate`.
        ``engine`` (``"hermit"`` or ``"rustdl"``) and ``timeout`` (seconds) are for the ``OWL-Direct`` regime, as for
        ``StarLayerGraph.query``, and are a ``ValueError`` with any other regime; ``recompute`` (``"onChange"``, ``"never"``,
        ``"always"``) says when the entailed copy of the data, shared with ``query(entailment=...)``, is made again (``None``: the
        built-in ``"onChange"``). A call's keyword overrides each.
        ``meta_shapes_extra`` is read once, so a generator works.

        Every graph is optional. A foreign graph is converted to an Oxigraph-backed one, and the conversion is run once here so
        that a graph that cannot be bound fails at construction. ``inference`` is not a graph: it is the entailment regime.

        **A bad shapes graph fails here, not at the first ``validate()``.** With a ``shacl_graph``, the shapes are read and
        compiled once at construction (the compiled plan is kept and ``validate()`` reuses it): every ``ShapeError`` from reading
        the shapes is raised by the constructor (a node shape with ``sh:path``, a ``sh:property`` value without ``sh:path``, a
        removed SHACL-AF construct, a malformed list, regex or flag, a constraint parameter of the wrong kind such as
        ``sh:minCount "many"``, whether or not any data has a focus node for it). With ``meta_shacl=True`` the meta-SHACL check
        also runs here (``MetaShaclError``), once; ``validate()`` does not repeat it. The constructor's ``shapes_graph_loader`` /
        ``ignore_imports`` are used: ``owl:imports`` the shapes graph declares that are not in it, with neither given, do
        not raise here (a call may still pass a loader), the shapes are then read at the first ``validate()`` as before. A
        call's ``meta_shacl=True`` on a processor built without it runs the check at that call (and is remembered).
        What is still found only when a focus node reaches it: node expressions (``sh:values``, ``sh:expression``, target
        expressions), the text of SPARQL queries, the validators of SPARQL-based components, and anything that depends on the
        data. ``shacl_graph`` set later is checked at the assignment; a shapes graph the caller edits in place is read again
        at the next ``validate()`` (so an error it introduces comes from there). A processor with no ``shacl_graph`` is not
        checked.
        """
        self._sources: dict[str, Any] = {
            "shacl_graph": shacl_graph,
            "ont_graph": ont_graph,
            "data_graph": data_graph,
            "scoring_graph": scoring_graph,
        }
        for bound_name in self._sources:  # fail at construction, not at first use, for a graph that cannot be bound
            self._bound(bound_name)
        self._checked = _adapter.CheckedShapes()
        self.inference = inference
        self.allow_warnings = allow_warnings
        self.allow_infos = allow_infos
        self.meta_shacl = meta_shacl
        self.meta_shapes_extra = None if meta_shapes_extra is None else tuple(meta_shapes_extra)
        self.ignore_imports = ignore_imports
        self.shapes_graph_loader = shapes_graph_loader
        self.max_iterations = max_iterations
        if max_triples is not _UNSET:
            _adapter.check_max_triples(max_triples)
        self.max_triples = max_triples
        self.subclass_of_in_shapes_graph = subclass_of_in_shapes_graph
        self.engine = engine
        self.timeout = timeout
        self.recompute = recompute
        self._check_shapes_graph()

    def _check_shapes_graph(self) -> None:
        """Read and compile the bound shapes graph (``ShapeError``), and run the meta-SHACL check when ``meta_shacl`` is bound
        (``MetaShaclError``, before the compile), so a bad shapes graph is refused when it is bound; ``validate()`` reuses both results.

        The constructor's ``shapes_graph_loader`` / ``ignore_imports`` decide the imports. Unsatisfied ``owl:imports`` with
        neither skip the check (a call may still bring a loader): the shapes are read at the first ``validate()``."""
        shapes = self.shacl_graph
        self._checked = _adapter.CheckedShapes()
        if shapes is None:
            return
        from starlayer.shacl.engine.imports import resolve_imports

        loader, ignore = self.shapes_graph_loader, bool(self.ignore_imports)
        try:
            resolved = resolve_imports(shapes, loader, ignore)
        except ExecutionError as error:  # unresolved owl:imports and no loader to resolve them with: a call may bring one
            if loader is not None:
                raise
            only_kind(error, "import")
            return
        checked = _adapter.CheckedShapes()
        if self.meta_shacl:  # first, as in validate(): a malformed shapes graph gets the meta-shapes' report, not a bare ShapeCompileError
            checked.check_meta(shapes, self.meta_shapes_extra or ())
        checked.compile(shapes, resolved)
        self._checked = checked

    def _option_defaults(self, names: Iterable[str] = _CONSTRUCTOR_OPTIONS) -> dict[str, Any]:
        """The constructor options among ``names`` that are set, to merge under a call's options."""
        values = {name: getattr(self, name) for name in names}
        return {
            name: value
            for name, value in values.items()
            if value is not _UNSET and (value is not None or name in _NONE_IS_A_VALUE)
        }

    def _bound(self, name: str) -> Any | None:
        source = self._sources[name]
        if source is None:
            return None
        batch = _adapter._PLAN_CACHE.get()
        if batch is not None:  # inside a batch: one conversion of a foreign graph, so the shapes are parsed once for the whole batch
            key = ("bound", name, id(source))
            if key not in batch:
                batch[key] = (source, normalize_to_starlayer_graph(source, name=name, force_default_union=name == "ont_graph"))
            return batch[key][1]
        return normalize_to_starlayer_graph(source, name=name, force_default_union=name == "ont_graph")

    @property
    def shacl_graph(self) -> Any | None:
        """The shapes graph, as an Oxigraph-backed graph (``StarLayerGraph`` / ``StarLayerDataset``)."""
        return self._bound("shacl_graph")

    @shacl_graph.setter
    def shacl_graph(self, value: Any | None) -> None:
        """Rebind the shapes graph, checked as at construction; a graph that fails leaves the processor as it was."""
        previous, previous_checked = self._sources["shacl_graph"], self._checked
        self._sources["shacl_graph"] = value
        try:
            self._check_shapes_graph()
        except Exception:
            self._sources["shacl_graph"], self._checked = previous, previous_checked
            raise

    @property
    def ont_graph(self) -> Any | None:
        """The ontology graph, as an Oxigraph-backed graph (``StarLayerGraph`` / ``StarLayerDataset``)."""
        return self._bound("ont_graph")

    @ont_graph.setter
    def ont_graph(self, value: Any | None) -> None:
        """Rebind the ontology graph; conversion, and any failure, is deferred to the next read."""
        self._sources["ont_graph"] = value

    @property
    def data_graph(self) -> Any | None:
        """The default data graph, as an Oxigraph-backed graph (``StarLayerGraph`` / ``StarLayerDataset``)."""
        return self._bound("data_graph")

    @data_graph.setter
    def data_graph(self, value: Any | None) -> None:
        """Rebind the default data graph; conversion, and any failure, is deferred to the next read."""
        self._sources["data_graph"] = value

    @property
    def scoring_graph(self) -> Any | None:
        """The scoring graph of ``shui:WidgetScore`` entries, as an Oxigraph-backed graph (``StarLayerGraph`` / ``StarLayerDataset``)."""
        return self._bound("scoring_graph")

    @scoring_graph.setter
    def scoring_graph(self, value: Any | None) -> None:
        """Rebind the scoring graph; conversion, and any failure, is deferred to the next read."""
        self._sources["scoring_graph"] = value

    def _resolve_data_graph(self, data_graph: Any | None) -> Any:
        resolved = data_graph if data_graph is not None else self.data_graph
        if resolved is None:
            raise ValueError(
                "No data_graph given, and this processor has no default data_graph bound at construction "
                "(StarShaclProcessor(data_graph=...))."
            )
        return resolved

    def _resolve_shacl_graph(self, shapes_graph_resource: Any | None) -> Any | None:
        """The bound shapes graph, or the module of it named by ``shapes_graph_resource`` (a ``sh:ShapesGraph`` node)."""
        if shapes_graph_resource is None:
            return self.shacl_graph
        if self.shacl_graph is None:
            raise ValueError(
                "shapes_graph_resource= needs a bound shapes graph to extract from - construct with "
                "StarShaclProcessor(shacl_graph=...)."
            )
        extracted = self.extract_shapes_graph(shapes_graph_resource)
        if extracted is None:
            raise ValueError(
                f"{shapes_graph_resource!r} is not typed `a sh:ShapesGraph` in this processor's own bound shacl_graph - "
                "extract_shapes_graph() returned None."
            )
        return _drop_nonmember_property_shape_refs(extracted)

    def target_nodes(
        self,
        *,
        data_graph: Any | None = None,
        shape_node: Any,
        shapes_graph_resource: Any | None = None,
        subclass_of_in_shapes_graph: bool | None = None,
        inference: Any | None = _UNSET,
        engine: str | None = None,
        timeout: float | None = None,
        recompute: str | None = None,
    ) -> tuple[Any, ...]:
        """The nodes ``shape_node`` targets in ``data_graph`` (default: the bound one), as ``validate()`` resolves them.
        ``subclass_of_in_shapes_graph`` defaults to the constructor's value (``None``: that value, else ``False``).
        ``inference`` replaces the constructor's regime(s) for this call (``None``: no regime of its own; ``<not set>``: the
        constructor's); the shapes graph's ``sh:entailment`` applies either way. ``engine``, ``timeout`` and ``recompute`` default to
        the constructor's values (see :func:`validate`)."""
        if inference is _UNSET:
            inference = self.inference
        entailment = self._entailment_options(engine, timeout, recompute)
        if subclass_of_in_shapes_graph is None:
            subclass_of_in_shapes_graph = bool(self.subclass_of_in_shapes_graph)
        return _adapter.target_nodes(
            data_graph=self._resolve_data_graph(data_graph),
            shacl_graph=self._resolve_shacl_graph(shapes_graph_resource),
            shape_node=shape_node,
            ont_graph=self.ont_graph,
            inference=inference,
            subclass_of_in_shapes_graph=subclass_of_in_shapes_graph,
            **entailment,
        )

    def target_shapes(
        self,
        *,
        node: Any,
        data_graph: Any | None = None,
        shapes_graph_resource: Any | None = None,
        subclass_of_in_shapes_graph: bool | None = None,
        inference: Any | None = _UNSET,
        engine: str | None = None,
        timeout: float | None = None,
        recompute: str | None = None,
    ) -> tuple[Any, ...]:
        """The shapes of the bound shapes graph that target ``node`` in ``data_graph`` (default: the bound one); see :func:`target_shapes`. The
        options default to the constructor's values, as for :meth:`target_nodes`."""
        if inference is _UNSET:
            inference = self.inference
        entailment = self._entailment_options(engine, timeout, recompute)
        if subclass_of_in_shapes_graph is None:
            subclass_of_in_shapes_graph = bool(self.subclass_of_in_shapes_graph)
        return _adapter.target_shapes(
            data_graph=self._resolve_data_graph(data_graph),
            shacl_graph=self._resolve_shacl_graph(shapes_graph_resource),
            node=node,
            ont_graph=self.ont_graph,
            inference=inference,
            subclass_of_in_shapes_graph=subclass_of_in_shapes_graph,
            **entailment,
        )

    def candidate_values(
        self,
        property_shape: Any,
        *,
        data_graph: Any | None = None,
        focus: Any | None = None,
        only_valid: bool = False,
        subclass_of_in_shapes_graph: bool | None = None,
    ) -> Candidates:
        """What a form can offer for the field of ``property_shape`` of the bound shapes graph, in ``data_graph`` (default: the bound one);
        see :func:`candidate_values`. ``subclass_of_in_shapes_graph`` defaults to the constructor's value, and ``only_valid`` applies the
        constructor's ``allow_warnings`` / ``allow_infos``."""
        if subclass_of_in_shapes_graph is None:
            subclass_of_in_shapes_graph = bool(self.subclass_of_in_shapes_graph)
        defaults = self._option_defaults(_VALIDATION_DEFAULTS)
        return _adapter.candidate_values(
            data_graph=self._resolve_data_graph(data_graph),
            shacl_graph=self._resolve_shacl_graph(None),
            property_shape=property_shape,
            focus=focus,
            only_valid=only_valid,
            subclass_of_in_shapes_graph=subclass_of_in_shapes_graph,
            conformance_disallows=_adapter.conformance_disallows_for(defaults.get("allow_warnings"), defaults.get("allow_infos")),
        )

    def value_form(self, property_shape: Any) -> str:
        """How the value of the field of ``property_shape`` of the bound shapes graph is held; see :func:`value_form`."""
        return _adapter.value_form(shacl_graph=self._resolve_shacl_graph(None), property_shape=property_shape)

    def check_value(
        self,
        property_shape: Any,
        focus: Any,
        value: Any,
        *,
        data_graph: Any | None = None,
        subclass_of_in_shapes_graph: bool | None = None,
    ) -> ValueCheck:
        """Whether ``value`` would be accepted for the field of ``property_shape`` of the bound shapes graph, for ``focus`` in
        ``data_graph`` (default: the bound one); see :func:`check_value`. The constructor's ``allow_warnings`` / ``allow_infos`` and
        ``subclass_of_in_shapes_graph`` apply."""
        if subclass_of_in_shapes_graph is None:
            subclass_of_in_shapes_graph = bool(self.subclass_of_in_shapes_graph)
        defaults = self._option_defaults(_VALIDATION_DEFAULTS)
        return _adapter.check_value(
            data_graph=self._resolve_data_graph(data_graph),
            shacl_graph=self._resolve_shacl_graph(None),
            property_shape=property_shape,
            focus=focus,
            value=value,
            subclass_of_in_shapes_graph=subclass_of_in_shapes_graph,
            conformance_disallows=_adapter.conformance_disallows_for(defaults.get("allow_warnings"), defaults.get("allow_infos")),
        )

    def form_model(
        self,
        node: Any,
        *,
        role: str = "editor",
        data_graph: Any | None = None,
        shapes: Any | None = None,
        empty: str = "auto",
        suggestions: bool = False,
        only_valid: bool = False,
        report: Any | None = None,
        widgets: Any | None = None,
        scoring_graph: Any | None = None,
        implemented: Any | None = None,
        inferred_graph: Any | None = None,
        placement: Any | None = None,
        subclass_of_in_shapes_graph: bool | None = None,
    ) -> FormModel:
        """The form of ``node`` by the bound shapes graph, in ``data_graph`` (default: the bound one); see :func:`form_model`.
        ``scoring_graph`` defaults to the bound one, ``subclass_of_in_shapes_graph`` to the constructor's value, and the constructor's
        ``allow_warnings`` / ``allow_infos`` apply to ``FormField.check`` and ``only_valid``. The shapes that target the node are
        found with the constructor's ``inference``, ontology graph, ``engine``, ``timeout`` and ``recompute``; ``sh:values`` values
        are computed on the data graph without that regime."""
        if subclass_of_in_shapes_graph is None:
            subclass_of_in_shapes_graph = bool(self.subclass_of_in_shapes_graph)
        if scoring_graph is None:
            scoring_graph = self.scoring_graph
        defaults = self._option_defaults(_VALIDATION_DEFAULTS)
        options = {"inference": self.inference, **self._entailment_options(None, None, None)}
        return _adapter.form_model(
            shapes_graph=self._resolve_shacl_graph(None),
            data_graph=self._resolve_data_graph(data_graph),
            node=node,
            role=role,
            shapes=shapes,
            empty=empty,
            suggestions=suggestions,
            only_valid=only_valid,
            report=report,
            widgets=widgets,
            scoring_graph=scoring_graph,
            implemented=implemented,
            inferred_graph=inferred_graph,
            placement=placement,
            subclass_of_in_shapes_graph=subclass_of_in_shapes_graph,
            conformance_disallows=_adapter.conformance_disallows_for(defaults.get("allow_warnings"), defaults.get("allow_infos")),
            target_options=options,
            ont_graph=self.ont_graph,
        )

    def _entailment_options(self, engine: Any, timeout: Any, recompute: Any) -> dict[str, Any]:
        """``engine``, ``timeout`` and ``recompute`` of a call that has no ``**kwargs``: the call's value, else the constructor's, else
        the built-in (left out)."""
        given = {"engine": engine, "timeout": timeout, "recompute": recompute}
        return {name: value if value is not None else getattr(self, name) for name, value in given.items()
                if (value if value is not None else getattr(self, name)) is not None}

    def validate(
        self,
        data_graph: Any | None = None,
        *,
        mode: str | ValidationMode | None = None,
        shapes_graph_loader: Callable[[Any], Any | None] | None = _UNSET,
        ignore_imports: bool = _UNSET,
        meta_shapes_extra: Iterable[Any] = _UNSET,
        data_graph_iri: Any | None = None,
        shapes_graph_resource: Any | None = None,
        shapes_graph_iri: Any | None = None,
        specification_graph: Any | None = None,
        include_used_configuration: bool = False,
        inference: Any | None = _UNSET,
        **kwargs: Any,
    ) -> ValidationReport:
        """Validates ``data_graph`` (default: the bound data graph) against the bound shapes graph; see :func:`validate`.

        ``inference`` (a regime IRI or an iterable of them) REPLACES the constructor's regime(s) for this call: ``None`` or an empty
        iterable means no regime of the call's own, ``<not set>`` means the constructor's. The shapes graph's ``sh:entailment``
        applies in every case, in addition. ``shapes_graph_resource`` validates against a
        named ``sh:ShapesGraph`` module of the bound shapes graph. ``shapes_graph_loader``, ``ignore_imports`` and
        ``meta_shapes_extra`` default to the constructor's values (``<not set>``: the loader ``None``, ``False``, ``()`` when
        none was bound); any value given here, ``None`` and ``False`` included, replaces them."""
        if inference is _UNSET:
            inference = self.inference
        data_graph = self._resolve_data_graph(data_graph)
        bound = self._option_defaults(_SHAPES_GRAPH_DEFAULTS)
        if shapes_graph_loader is _UNSET:
            shapes_graph_loader = bound.get("shapes_graph_loader")
        if ignore_imports is _UNSET:
            ignore_imports = bound.get("ignore_imports", False)
        if meta_shapes_extra is _UNSET:
            meta_shapes_extra = bound.get("meta_shapes_extra", ())
        return _adapter.validate(
            data_graph=data_graph,
            shacl_graph=self.shacl_graph,
            ont_graph=self.ont_graph,
            inference=inference,
            mode=mode,
            options=kwargs,
            option_defaults=self._option_defaults(_VALIDATION_DEFAULTS),
            shapes_graph_loader=shapes_graph_loader,
            ignore_imports=ignore_imports,
            meta_shapes_extra=meta_shapes_extra,
            data_graph_iri=data_graph_iri,
            shapes_graph_iri=shapes_graph_iri,
            shapes_graph_resource=shapes_graph_resource,
            specification_graph=specification_graph,
            include_used_configuration=include_used_configuration,
            checked=self._checked,
        )

    def validate_each(self, dataset: Any | None = None, **kwargs: Any) -> dict[Any, ValidationReport]:
        """Validates each graph of ``dataset`` (default: the bound data graph, which must then be a dataset) with :meth:`validate`; the
        shapes are parsed once for the whole batch. ``dataset`` and the result's keys are as for the module function
        :func:`validate_each`. The keywords of :meth:`validate`, ``inference`` included, apply to every graph."""
        if dataset is None:
            dataset = self.data_graph
        with _adapter.shared_plans():
            return {key: self.validate(data_graph, **kwargs) for key, data_graph in _each_items(dataset)}

    def apply_rules(
        self,
        data_graph: Any | None = None,
        include_source_rule_provenance: bool = False,
        rule_set: Any | None = None,
        shapes_graph_resource: Any | None = None,
        inference: Any | None = _UNSET,
        **kwargs: Any,
    ) -> RulesResult:
        """Runs the rules of the bound shapes graph over ``data_graph`` (default: the bound one); see :func:`apply_rules`.
        ``shapes_graph_resource`` selects a named ``sh:ShapesGraph`` module of the bound shapes graph. The constructor's options
        that rule execution uses are the defaults of the keywords of the same name here; ``allow_warnings`` and ``allow_infos``
        stay defaults of ``validate()`` only. ``inference`` replaces the constructor's regime(s) for
        this call (``None``: none of its own; ``<not set>``: the constructor's), for the entailment the rules match over; the
        shapes graph's ``sh:entailment`` applies too."""
        if inference is _UNSET:
            inference = self.inference
        data_graph = self._resolve_data_graph(data_graph)
        return apply_rules(
            data_graph,
            self._resolve_shacl_graph(shapes_graph_resource),
            self.ont_graph,
            include_source_rule_provenance=include_source_rule_provenance,
            rule_set=rule_set,
            inference=inference,
            **{**self._option_defaults(_RULES_DEFAULTS), **kwargs},  # no mode=, and no validation defaults: constructor values, then the call's
        )

    def evaluate(
        self,
        data_graph: Any | None = None,
        *,
        shapes_graph_resource: Any | None = None,
        focus_nodes: Any | None = None,
        properties: Any | None = None,
        rules_entailment: bool = False,
        validate: bool = False,
        inference: Any | None = _UNSET,
        engine: str | None = None,
        timeout: float | None = None,
        recompute: str | None = None,
    ) -> Any:
        """Computes the ``sh:values`` / ``sh:defaultValue`` virtual properties of the bound shapes graph over ``data_graph``
        (default: the bound one); see :func:`evaluate`. ``inference`` replaces the constructor's regime(s) for this call
        (``None``: no regime of its own; ``<not set>``: the constructor's); the shapes graph's ``sh:entailment`` applies either
        way. ``engine``, ``timeout`` and ``recompute`` default to the constructor's values (see :func:`validate`). The other options of
        :meth:`validate` (``allow_warnings`` and so on) are not taken."""
        if inference is _UNSET:
            inference = self.inference
        entailment = self._entailment_options(engine, timeout, recompute)
        data_graph = self._resolve_data_graph(data_graph)
        return _adapter.evaluate(
            data_graph,
            self._resolve_shacl_graph(shapes_graph_resource),
            self.ont_graph,
            inference=inference,
            focus_nodes=focus_nodes,
            properties=properties,
            rules_entailment=rules_entailment,
            validate=validate,
            **entailment,
        )

    def select_widgets(
        self,
        *,
        shape_node: Any,
        focus_node: Any | None = None,
        role: str,
        data_graph: Any | None = None,
        scoring_graph: Any | None = None,
        shapes_graph_resource: Any | None = None,
        per: str = "node",
    ) -> dict[Any, Any]:
        """Chooses a SHACL 1.2 UI widget for each property of the node shape ``shape_node``, using the bound shapes graph.

        Delegates to :func:`starlayer.shacl.select_widgets`; this method supplies the bound shapes graph, the bound
        ``scoring_graph`` and (when a ``focus_node`` is given) the bound ``data_graph``. Each can be overridden per call.

        Args:
            shape_node: A ``sh:NodeShape`` of the shapes graph; its ``sh:property`` values are walked.
            focus_node: Optional node whose data a matcher's ``shui:dataGraphShape`` is checked against.
            role: ``"editor"`` or ``"viewer"``.
            data_graph: The graph holding ``focus_node``; only needed when ``focus_node`` is given.
            scoring_graph: Catalog of ``shui:WidgetScore`` / ``shui:WidgetAcceptMatcher`` entries (default: the bound one; pass an
                empty graph to ignore a bound catalog for one call).
            shapes_graph_resource: A named ``sh:ShapesGraph`` module of the bound shapes graph.
            per: ``"node"`` (the default) or ``"shape"``: with ``"shape"`` the answer is once per property shape, a
                ``WidgetChoice`` each, to finish per node with ``choice.resolve(focus_node, data_graph)``.

        Returns:
            ``{property_shape: widget}``, with ``None`` for a property that has no widget (or ``{property_shape: WidgetChoice}``).

        Raises:
            ValueError: no shapes graph is bound, or a ``focus_node`` is given with no data graph available.
        """
        from starlayer.shacl.ui.widget_selection import select_widgets

        shapes_graph = self._resolve_shacl_graph(shapes_graph_resource)
        if shapes_graph is None:
            raise ValueError("select_widgets() needs a shapes graph, and this processor has no shacl_graph bound.")
        if focus_node is not None:
            data_graph = self._resolve_data_graph(data_graph)
        if scoring_graph is None:
            scoring_graph = self.scoring_graph
        return select_widgets(
            shape_node=shape_node,
            focus_node=focus_node,
            data_graph=data_graph,
            shapes_graph=shapes_graph,
            scoring_graph=scoring_graph,
            role=role,  # type: ignore[arg-type]
            per=per,  # type: ignore[arg-type]
        )

    def extract_subgraph(
        self,
        data_graph: Any | None = None,
        *,
        shape: Any | None = None,
        focus_node: Any | None = None,
        shapes_graph_resource: Any | None = None,
        inference: Any | None = _UNSET,
        include_targets: bool = True,
    ) -> Any:
        """The subgraph of ``data_graph`` (default: the bound one) that ``shape`` and ``focus_node`` cover, using the bound shapes graph and
        ontology graph; see :func:`starlayer.shacl.extract_subgraph`. ``inference`` replaces the constructor's regime(s) for this call
        (``None``: no regime of its own; ``<not set>``: the constructor's)."""
        from starlayer.shacl.subgraph_extraction import extract_subgraph

        if inference is _UNSET:
            inference = self.inference
        return extract_subgraph(
            self._resolve_data_graph(data_graph),
            self._resolve_shacl_graph(shapes_graph_resource),
            self.ont_graph,
            shape=shape,
            focus_node=focus_node,
            inference=inference,
            include_targets=include_targets,
        )

    def select_widget(
        self,
        *,
        shape_node: Any,
        role: str,
        focus_node: Any | None = None,
        data_graph: Any | None = None,
        scoring_graph: Any | None = None,
        shapes_graph_resource: Any | None = None,
        implemented: Any | None = None,
        on_report: Any | None = None,
    ) -> Any | None:
        """The ``shui:editor`` / ``shui:viewer`` widget of the property shape ``shape_node``, using the bound shapes graph; see
        :func:`starlayer.shacl.select_widget`. Like :meth:`select_widgets`, the bound ``scoring_graph`` is used unless one is given, and the bound
        ``data_graph`` is used when a ``focus_node`` is given and no ``data_graph``.

        Raises:
            ValueError: no shapes graph is bound, or a ``focus_node`` is given with no data graph available.
        """
        from starlayer.shacl.ui.widget_selection import select_widget

        shapes_graph = self._resolve_shacl_graph(shapes_graph_resource)
        if shapes_graph is None:
            raise ValueError("select_widget() needs a shapes graph, and this processor has no shacl_graph bound.")
        if focus_node is not None:
            data_graph = self._resolve_data_graph(data_graph)
        if scoring_graph is None:
            scoring_graph = self.scoring_graph
        return select_widget(
            shape_node=shape_node,
            focus_node=focus_node,
            data_graph=data_graph,
            shapes_graph=shapes_graph,
            scoring_graph=scoring_graph,
            role=role,  # type: ignore[arg-type]
            implemented=implemented,
            on_report=on_report,
        )

    def explain_widgets(
        self,
        *,
        shape_node: Any,
        role: str,
        data_graph: Any | None = None,
        focus_nodes: Any = (),
        sample: int = 3,
        scoring_graph: Any | None = None,
        shapes_graph_resource: Any | None = None,
    ) -> Any:
        """Every candidate widget for the property shape ``shape_node`` and why each is or is not chosen, using the bound shapes graph; see
        :func:`starlayer.shacl.explain_widgets`. The bound ``scoring_graph`` is used unless one is given, and the bound ``data_graph`` when
        ``focus_nodes`` are given and no ``data_graph``.

        Raises:
            ValueError: no shapes graph is bound, or ``focus_nodes`` are given with no data graph available.
        """
        from starlayer.shacl.ui.widget_selection import explain_widgets

        shapes_graph = self._resolve_shacl_graph(shapes_graph_resource)
        if shapes_graph is None:
            raise ValueError("explain_widgets() needs a shapes graph, and this processor has no shacl_graph bound.")
        if len(list(focus_nodes)) > 0:
            data_graph = self._resolve_data_graph(data_graph)
        if scoring_graph is None:
            scoring_graph = self.scoring_graph
        return explain_widgets(
            shape_node=shape_node,
            shapes_graph=shapes_graph,
            scoring_graph=scoring_graph,
            role=role,  # type: ignore[arg-type]
            data_graph=data_graph,
            focus_nodes=focus_nodes,
            sample=sample,
        )

    def close_shape(self, shape: Any, *, shapes_graph_resource: Any | None = None) -> Any:
        """A copy of the whole bound shapes graph in which ``shape`` and the shapes it reaches as a value node's complete
        description (``sh:node``, ``sh:qualifiedValueShape``, the members of ``sh:and`` / ``sh:or`` / ``sh:xone``) are
        ``sh:closed true``: the strict form an ``extract_subgraph`` fragment is checked against. Shapes that are not reached stay as
        they are; nothing is removed. See ``shacl.engine.shapes_graphs.close_shape`` for the exact rules."""
        shacl_graph_input = self._resolve_shacl_graph(shapes_graph_resource)
        if shacl_graph_input is None:
            raise ValueError(
                "close_shape() needs a bound shapes graph - construct with StarShaclProcessor(shacl_graph=...)."
            )
        return _adapter.close_shape(shacl_graph_input, shape)

    def extract_shapes_graph(self, shapes_graph_iri: Any, *, include_referenced: bool = False) -> Any | None:
        """Extracts the ``sh:ShapesGraph`` named ``shapes_graph_iri`` as a standalone graph (its members, with their blank-node
        closures and the declared prefixes), or ``None`` when the bound shapes graph has no such resource.

        With ``include_referenced=True`` the extract also holds every shape the members reference, so it can be validated on its
        own; without it, the extract is exactly the module's members, and a ``sh:property`` link to a property shape left behind is
        dangling."""
        if self.shacl_graph is None:
            raise ValueError(
                "extract_shapes_graph() needs a bound shapes graph - construct with StarShaclProcessor(shacl_graph=...)."
            )
        return _adapter.extract_shapes_graph(self.shacl_graph, shapes_graph_iri, include_referenced=include_referenced)


def __getattr__(name: str) -> Any:
    """``StarShaclSchema``, the old name of ``StarShaclProcessor``: the same class, with a DeprecationWarning."""
    if name == "StarShaclSchema":
        import warnings

        warnings.warn(
            "StarShaclSchema is renamed StarShaclProcessor; the old name will be removed",
            DeprecationWarning,
            stacklevel=2,
        )
        return StarShaclProcessor
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
