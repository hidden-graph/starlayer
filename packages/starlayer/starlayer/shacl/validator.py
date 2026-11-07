"""The public SHACL API: ``validate``, ``validate_each``, ``apply_rules``, ``evaluate`` and ``StarShaclSchema``.

Each call normalises its graphs and hands them to the native SHACL 1.2 engine (``starlayer.shacl_engine``) through
``starlayer.shacl._adapter``. ``StarShaclSchema`` binds a shapes graph (and optionally an ontology, a data graph, a scoring
graph and an entailment regime) once and offers the same operations as methods.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable
from typing import Any

from starlayer.shacl import _adapter
from starlayer.shacl.normalization import normalize_to_starlayer_graph
from starlayer.shacl.results import RulesResult, ValidationResult
from starlayer.shacl.validation_modes import ValidationMode
from starlayer.shacl_engine.terms import RDF, SH, BlankNode, n3


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
) -> ValidationResult:
    """Validates ``data_graph`` against ``shacl_graph`` per SHACL 1.2 and returns a ``ValidationResult``.

    Args:
        data_graph: The RDF data to validate: an ``StarLayerGraph`` / ``StarLayerDataset`` (used as it is) or an rdflib / old-style ``StarLayerGraph``
            (copied into an ``StarLayerGraph``). It is never changed unless ``inplace=True``.
        shacl_graph: The shapes graph. ``None`` reads the shapes from ``data_graph`` itself.
        ont_graph: An optional ontology graph. Its axioms (``rdfs:domain``, ``rdfs:subClassOf`` ...) are visible to entailment, but
            its triples are never copied into ``data_graph``.
        mode: A named preset of options (``"validation"``, ``"rules"`` or ``"debug"``); any of its options can be overridden per
            call through ``**kwargs``.
        shapes_graph_loader: Resolves the shapes graph's ``owl:imports``. With no loader, an import that is not already in the
            graph raises ``ValueError`` unless ``ignore_imports=True``.
        ignore_imports: Do not complain about imports that cannot be resolved.
        meta_shapes_extra: Extra graphs for the shapes-about-shapes check when ``meta_shacl=True``.
        data_graph_iri, shapes_graph_iri: Recorded on the report as ``sh:usedDataGraph`` / ``sh:usedShapesGraph``; each defaults
            to the graph's own identifier when that is an IRI.
        shapes_graph_resource: Validate against a named ``sh:ShapesGraph`` module of ``shacl_graph`` (its IRI becomes
            ``sh:usedShapesGraph``), or, for an IRI that is not a module of it, only tag the report with that IRI.
        specification_graph: Lets Profiling derive ``dcterms:conformsTo`` from the derived ``sh:conformsTo``.
        include_used_configuration: Also record the options in effect on the report.
        **kwargs: Option overrides: ``inference`` (an entailment regime IRI such as ``ENTAILMENT.RDFS``, or an iterable of them),
            ``inplace``, ``meta_shacl``, ``advanced`` (False: do not run rules), ``allow_warnings``, ``allow_infos``,
            ``abort_on_first``, ``max_validation_depth``, ``invalid_terms`` (``"lenient"``: process terms that are not RDF terms, such as a
            relative IRI, as opaque stand-ins instead of raising ``TermError``). An unknown option is a ``TypeError``.

    Returns:
        A ``ValidationResult``: ``conforms``, ``report_graph`` (an ``StarLayerGraph``) and ``report_text``, ``data_graph`` (the caller's graph when
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


def validate_each(
    data_graphs: Iterable[Any],
    shacl_graph: Any | None = None,
    ont_graph: Any | None = None,
    **kwargs: Any,
) -> dict[int, ValidationResult]:
    """Validates each graph of ``data_graphs`` against the same ``shacl_graph`` / ``ont_graph``; the shapes are parsed once for the
    whole batch. ``kwargs`` are those of :func:`validate`. Returns ``{index: ValidationResult}``."""
    with _adapter.shared_plans():
        return {i: validate(data_graph, shacl_graph, ont_graph, **kwargs) for i, data_graph in enumerate(data_graphs)}


def evaluate(
    data_graph: Any,
    shacl_graph: Any | None = None,
    ont_graph: Any | None = None,
    *,
    inference: Any | None = None,
    focus_nodes: Any | None = None,
    properties: Any | None = None,
    rules_entailment: bool = False,
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
        focus_nodes: Restrict evaluation to these focus nodes (``None``: every node the shapes target).
        properties: Restrict evaluation to property shapes with one of these ``sh:path`` IRIs (``None``: all).
        rules_entailment: Also run the rules the shapes graph names in ``sh:entailment`` first.
    """
    return _adapter.evaluate(
        data_graph,
        shacl_graph,
        ont_graph,
        inference=inference,
        focus_nodes=focus_nodes,
        properties=properties,
        rules_entailment=rules_entailment,
    )


def apply_rules(
    data_graph: Any,
    shacl_graph: Any | None = None,
    ont_graph: Any | None = None,
    include_source_rule_provenance: bool = False,
    rule_set: Any | None = None,
    **kwargs: Any,
) -> RulesResult:
    """Executes the SHACL rules of ``shacl_graph`` against a working copy of ``data_graph``, then validates the result.

    Covers ``sh:TripleRule`` and ``sh:SPARQLRule`` (shape-attached, in rule sets, or global) and ``sh:sourceRule`` provenance.
    ``data_graph`` is never changed.

    Args:
        data_graph: The data the rules run over: an Oxigraph-backed graph (an rdflib / old-style ``StarLayerGraph`` is copied into one).
        shacl_graph: The shapes graph holding the rules; ``None`` reads them from ``data_graph``.
        ont_graph: An optional ontology graph, visible to entailment only.
        include_source_rule_provenance: Record, for every inferred triple, a reifier ``_:r rdf:reifies <<( s p o )>>`` with
            ``_:r sh:sourceRule <rule>`` (Inference Rules section 9).
        rule_set: Run only the rules of this ``sh:RuleSet`` (an IRI, or an iterable of IRIs).
        **kwargs: The options of :func:`validate` (including ``inference``), used for the final validation pass; and the rule limits
            ``max_iterations`` (default 1000: more iterations than that without reaching a fixpoint raise ``RuleError``) and
            ``max_triples`` (stop when more triples than that are inferred).

    Returns:
        A ``RulesResult``: ``inferred_graph`` holds only the triples the rules produced (and the ``sh:sourceRule`` reifiers);
        ``validation`` is the ``ValidationResult`` over the complete evaluation graph: base, inferred and entailed triples.
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
) -> tuple[Any, ...]:
    """The nodes ``shape_node`` targets in ``data_graph``, in declaration order and without duplicates: the nodes ``validate()``
    reports on for that shape (``sh:targetNode``, including a node expression, ``sh:targetClass`` with subclasses,
    ``sh:targetSubjectsOf``, ``sh:targetObjectsOf``, ``sh:targetWhere``, data-graph ``sh:shape`` and implicit class targets).

    ``shacl_graph=None`` reads the shapes from ``data_graph``. The shapes graph's own ``sh:entailment`` and ``inference`` (an
    entailment regime IRI or an iterable of them) are applied first, over the data graph and ``ont_graph``, without changing
    either."""
    return _adapter.target_nodes(
        data_graph=data_graph, shacl_graph=shacl_graph, shape_node=shape_node, ont_graph=ont_graph, inference=inference
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

    The genuine report is a fresh node that nothing in the graph refers to, except possibly a ``sh:validationReport`` link;
    among several candidates the one with the most ``sh:result`` wins, ties broken by identifier, so the answer never depends on
    iteration order. ``None`` when there is no report node at all."""
    candidates = sorted({s for s, _, _ in report_graph.triples((None, RDF.type, SH.ValidationReport))}, key=n3)  # str-ok: a tie-break
    if len(candidates) <= 1:
        return candidates[0] if candidates else None

    def only_linked_to(node: Any) -> bool:
        return all(p == SH.validationReport for _, p, _ in report_graph.triples((None, None, node)))

    roots = [n for n in candidates if only_linked_to(n)]
    if len(roots) == 1:
        return roots[0]
    pool = roots or candidates
    return max(pool, key=lambda n: (len(list(report_graph.objects(n, SH.result))), n3(n)))


class StarShaclSchema:
    """A shapes graph (and optionally an ontology graph, a default data graph, a scoring graph and an entailment regime), bound once,
    to validate, run rules against, or evaluate node expressions over any number of data graphs.

    Construct one per shapes set (``PersonSchema = StarShaclSchema(person_shapes)``), then call ``validate`` / ``apply_rules`` /
    ``evaluate`` with whatever data graph you are checking. ``select_widgets`` needs no data graph: it chooses SHACL 1.2 UI widgets
    from the shapes graph alone. Shape-driven subgraph extraction is the plain function ``starlayer.shacl.extract_subgraph()``.

    ``inference`` is an entailment regime IRI (``ENTAILMENT.RDFS``) or an iterable of them, applied to the data graph of every call
    together with the shapes graph's own ``sh:entailment``.
    """

    def __init__(
        self,
        shacl_graph: Any | None = None,
        ont_graph: Any | None = None,
        *,
        data_graph: Any | None = None,
        scoring_graph: Any | None = None,
        inference: Any | None = None,
    ) -> None:
        self._sources: dict[str, Any] = {
            "shacl_graph": shacl_graph,
            "ont_graph": ont_graph,
            "data_graph": data_graph,
            "scoring_graph": scoring_graph,
        }
        for bound_name in self._sources:  # fail at construction, not at first use, for a graph that cannot be bound
            self._bound(bound_name)
        self.inference = inference

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
        self._sources["shacl_graph"] = value

    @property
    def ont_graph(self) -> Any | None:
        """The ontology graph, as an Oxigraph-backed graph (``StarLayerGraph`` / ``StarLayerDataset``)."""
        return self._bound("ont_graph")

    @ont_graph.setter
    def ont_graph(self, value: Any | None) -> None:
        self._sources["ont_graph"] = value

    @property
    def data_graph(self) -> Any | None:
        """The default data graph, as an Oxigraph-backed graph (``StarLayerGraph`` / ``StarLayerDataset``)."""
        return self._bound("data_graph")

    @data_graph.setter
    def data_graph(self, value: Any | None) -> None:
        self._sources["data_graph"] = value

    @property
    def scoring_graph(self) -> Any | None:
        """The scoring graph of ``shui:WidgetScore`` entries, as an Oxigraph-backed graph (``StarLayerGraph`` / ``StarLayerDataset``)."""
        return self._bound("scoring_graph")

    @scoring_graph.setter
    def scoring_graph(self, value: Any | None) -> None:
        self._sources["scoring_graph"] = value

    def _resolve_data_graph(self, data_graph: Any | None) -> Any:
        resolved = data_graph if data_graph is not None else self.data_graph
        if resolved is None:
            raise ValueError(
                "No data_graph given, and this schema has no default data_graph bound at construction "
                "(StarShaclSchema(data_graph=...))."
            )
        return resolved

    def _resolve_shacl_graph(self, shapes_graph_resource: Any | None) -> Any | None:
        """The bound shapes graph, or the module of it named by ``shapes_graph_resource`` (a ``sh:ShapesGraph`` node)."""
        if shapes_graph_resource is None:
            return self.shacl_graph
        if self.shacl_graph is None:
            raise ValueError(
                "shapes_graph_resource= needs a bound shapes graph to extract from - construct with "
                "StarShaclSchema(shacl_graph=...)."
            )
        extracted = self.extract_shapes_graph(shapes_graph_resource)
        if extracted is None:
            raise ValueError(
                f"{shapes_graph_resource!r} is not typed `a sh:ShapesGraph` in this schema's own bound shacl_graph - "
                "extract_shapes_graph() returned None."
            )
        return _drop_nonmember_property_shape_refs(extracted)

    def target_nodes(
        self, *, data_graph: Any | None = None, shape_node: Any, shapes_graph_resource: Any | None = None
    ) -> tuple[Any, ...]:
        """The nodes ``shape_node`` targets in ``data_graph`` (default: the bound one), as ``validate()`` resolves them."""
        return _adapter.target_nodes(
            data_graph=self._resolve_data_graph(data_graph),
            shacl_graph=self._resolve_shacl_graph(shapes_graph_resource),
            shape_node=shape_node,
            ont_graph=self.ont_graph,
            inference=self.inference,
        )

    def validate(
        self,
        data_graph: Any | None = None,
        *,
        mode: str | ValidationMode | None = None,
        shapes_graph_loader: Callable[[Any], Any | None] | None = None,
        ignore_imports: bool = False,
        meta_shapes_extra: Iterable[Any] = (),
        data_graph_iri: Any | None = None,
        shapes_graph_resource: Any | None = None,
        include_used_configuration: bool = False,
        **kwargs: Any,
    ) -> ValidationResult:
        """Validates ``data_graph`` (default: the bound data graph) against the bound shapes graph; see :func:`validate`.

        ``inference`` is bound at construction, not per call (``TypeError`` here). ``shapes_graph_resource`` validates against a
        named ``sh:ShapesGraph`` module of the bound shapes graph."""
        if "inference" in kwargs:
            raise TypeError(
                "validate() no longer accepts inference= directly - it's bound once at "
                "construction instead (StarShaclSchema(inference=...)). Construct a "
                "second StarShaclSchema if you need a different regime."
            )
        data_graph = self._resolve_data_graph(data_graph)
        return _adapter.validate(
            data_graph=data_graph,
            shacl_graph=self.shacl_graph,
            ont_graph=self.ont_graph,
            inference=self.inference,
            mode=mode,
            options=kwargs,
            shapes_graph_loader=shapes_graph_loader,
            ignore_imports=ignore_imports,
            meta_shapes_extra=meta_shapes_extra,
            data_graph_iri=data_graph_iri,
            shapes_graph_resource=shapes_graph_resource,
            include_used_configuration=include_used_configuration,
        )

    def validate_each(self, data_graphs: Iterable[Any] | None = None, **kwargs: Any) -> dict[int, ValidationResult]:
        """Validates each graph of ``data_graphs`` (default: just the bound data graph) with :meth:`validate`; the shapes are parsed
        once for the whole batch. Returns ``{index: ValidationResult}``."""
        if data_graphs is None:
            data_graphs = (self.data_graph,)
        with _adapter.shared_plans():
            return {i: self.validate(data_graph, **kwargs) for i, data_graph in enumerate(data_graphs)}

    def apply_rules(
        self,
        data_graph: Any | None = None,
        include_source_rule_provenance: bool = False,
        rule_set: Any | None = None,
        shapes_graph_resource: Any | None = None,
        **kwargs: Any,
    ) -> RulesResult:
        """Runs the rules of the bound shapes graph over ``data_graph`` (default: the bound one); see :func:`apply_rules`.
        ``shapes_graph_resource`` selects a named ``sh:ShapesGraph`` module of the bound shapes graph."""
        data_graph = self._resolve_data_graph(data_graph)
        return apply_rules(
            data_graph,
            self._resolve_shacl_graph(shapes_graph_resource),
            self.ont_graph,
            include_source_rule_provenance=include_source_rule_provenance,
            rule_set=rule_set,
            inference=self.inference,
            **kwargs,
        )

    def evaluate(
        self,
        data_graph: Any | None = None,
        *,
        shapes_graph_resource: Any | None = None,
        focus_nodes: Any | None = None,
        properties: Any | None = None,
        rules_entailment: bool = False,
    ) -> Any:
        """Computes the ``sh:values`` / ``sh:defaultValue`` virtual properties of the bound shapes graph over ``data_graph``
        (default: the bound one); see :func:`evaluate`."""
        data_graph = self._resolve_data_graph(data_graph)
        return _adapter.evaluate(
            data_graph,
            self._resolve_shacl_graph(shapes_graph_resource),
            self.ont_graph,
            inference=self.inference,
            focus_nodes=focus_nodes,
            properties=properties,
            rules_entailment=rules_entailment,
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
        from starlayer.shacl.ui_widget_selection import select_widgets

        shapes_graph = self._resolve_shacl_graph(shapes_graph_resource)
        if shapes_graph is None:
            raise ValueError("select_widgets() needs a shapes graph, and this schema has no shacl_graph bound.")
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

    def close_shape(self, shape: Any, *, shapes_graph_resource: Any | None = None) -> Any:
        """A copy of the whole bound shapes graph in which ``shape`` and the shapes it reaches as a value node's complete
        description (``sh:node``, ``sh:qualifiedValueShape``, the members of ``sh:and`` / ``sh:or`` / ``sh:xone``) are
        ``sh:closed true``: the strict form an ``extract_subgraph`` fragment is checked against. Shapes that are not reached stay as
        they are; nothing is removed. See ``shacl_engine.shapes_graphs.close_shape`` for the exact rules."""
        shacl_graph_input = self._resolve_shacl_graph(shapes_graph_resource)
        if shacl_graph_input is None:
            raise ValueError(
                "close_shape() needs a bound shapes graph - construct with StarShaclSchema(shacl_graph=...)."
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
                "extract_shapes_graph() needs a bound shapes graph - construct with StarShaclSchema(shacl_graph=...)."
            )
        return _adapter.extract_shapes_graph(self.shacl_graph, shapes_graph_iri, include_referenced=include_referenced)
