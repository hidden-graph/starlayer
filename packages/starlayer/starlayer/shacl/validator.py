from __future__ import annotations

import contextvars
from collections.abc import Callable, Iterable
from typing import Any

from rdflib import BNode, Graph, Literal, Namespace, URIRef
from rdflib.collection import Collection
from rdflib.namespace import OWL, RDF, RDFS, NamespaceManager

from starlayer.shacl.adapters import TripleTermAdapter, TripleTermGraph
from starlayer.shacl.engine import (
    ComponentRequest,
    normalize_graph_inputs,
    normalize_to_starlayer_graph,
)
from starlayer.shacl.engine import (
    build_report as native_build_report,
)
from starlayer.shacl.engine import (
    evaluate_component as native_evaluate_component,
)
from starlayer.shacl.engine import (
    target_nodes as native_target_nodes,
)
from starlayer.shacl.native_components import (
    _RDF_REIFIES,
    SHAPE_EXPECTING_PREDICATES,
    _ambient_shapes_graph_prefixes,
    _get_tt_adapter,
    ensure_shape_typed,
    register_native_components,
    shape_reference_nodes,
)
from starlayer.shacl.results import (
    ExecutionDiagnostics,
    RulesResult,
    ValidationResult,
)
from starlayer.shacl.types import ensure_graph_mutable
from starlayer.shacl.validation_modes import ValidationMode, resolve_mode_options

SH = Namespace("http://www.w3.org/ns/shacl#")
SHNEX = Namespace("http://www.w3.org/ns/shacl-node-expr#")
SPARQL_EXPR_NS = Namespace("http://www.w3.org/ns/sparql#")
DCTERMS = Namespace("http://purl.org/dc/terms/")

_LITERAL_ONLY_COMPONENTS: dict[str, Any] = {
    "pattern": SH.PatternConstraintComponent,
    "datatype": SH.DatatypeConstraintComponent,
    "languageIn": SH.LanguageInConstraintComponent,
    "minLength": SH.MinLengthConstraintComponent,
    "maxLength": SH.MaxLengthConstraintComponent,
}

_STRUCTURAL_COMPONENTS: dict[str, Any] = {
    "hasValue": SH.HasValueConstraintComponent,
    "in": SH.InConstraintComponent,
    "equals": SH.EqualsConstraintComponent,
    "disjoint": SH.DisjointConstraintComponent,
}


class _RawGraphView:
    """Minimal ``sg``-shaped wrapper exposing just ``.graph``, so
    ``starlayer.shacl.node_expressions._is_shnex_expr``/
    ``starlayer.shacl.sparql_node_expressions.is_sparql_expr`` (which only ever
    read ``sg.graph``) can be used to test whether a candidate node is
    actually a well-formed ``shnex:``/``sparql:`` expression before paying
    for a real, harvested ``pyshacl.shapes_graph.ShapesGraph`` - needed only
    once a candidate is confirmed and must actually be evaluated (e.g. via
    ``eval_expr``, for operators like ``shnex:filterShape`` that check
    shape conformance).
    """

    def __init__(self, graph: Any) -> None:
        self.graph = graph


class StarShaclSchema:
    """A SHACL schema: a bound shapes graph plus an optional ontology
    graph, to validate, infer rules against, or evaluate node
    expressions over any number of data graphs.

    ``self.shacl_graph``/``self.ont_graph`` are each a reference to
    their own separate graph - this class does not itself *hold* triples
    the way ``StarLayerGraph`` does. Composition, not inheritance: there
    is no real "is-a" relationship available between it and any
    existing rdflib/pyshacl class - pySHACL's own main entry point,
    ``validate()``, is a stateless one-shot function, not a long-lived
    object to subclass, and this class unifies several independent
    capabilities (``validate``/``apply_rules``/``evaluate``) rather than
    specializing any one of them. Construct one per distinct shapes-set
    (``PersonSchema = StarShaclSchema(person_shapes)``,
    ``ProductSchema = StarShaclSchema(product_shapes)``, ...), then call
    ``validate``/``apply_rules``/``evaluate`` against whatever data graph
    you're checking. ``select_widgets`` is the one method that needs no data
    graph at all - it chooses SHACL 1.2 UI widgets from the shapes graph alone. Shape-driven subgraph extraction is a separate, plain
    function (``starlayer.shacl.extract_subgraph()``), not a method here -
    see its own docstring, and the subgraph-extraction guide, for why.

    Adds RDF 1.2/triple-term adaptation around pySHACL, which understands
    neither triple terms nor SHACL 1.2's own predicates natively.
    """

    def __init__(
        self,
        shacl_graph: Any | None = None,
        ont_graph: Any | None = None,
        *,
        data_graph: Any | None = None,
        scoring_graph: Any | None = None,
        inference: Any | None = None,
        adapter: TripleTermAdapter | None = None,
        validate_fn: Callable[..., tuple[bool, Graph, str]] | None = None,
    ) -> None:
        """Bind a shapes graph (plus optional ontology/data graphs and an
        entailment regime) once, so every processing method
        (``validate``/``apply_rules``/``evaluate``/``target_nodes``) can
        be called repeatedly without re-passing the same arguments.

        Args:
            shacl_graph: The SHACL shapes graph to validate against.
                Normalized once, here, rather than per-call: every method
                below reads this same object every time, so
                ``apply_rules()``'s own separate
                ``normalize_graph_inputs(self.shacl_graph, ...)`` call
                (for ``rule_set``/``_global_sparql_rule_triples`` - needs
                blank-node identity to match whatever ``self.validate()``
                ends up using internally) gets the identical,
                already-normalized object back - no second, independent
                normalization that could silently diverge.
            ont_graph: An optional ontology graph consulted for
                entailment and other axiom lookups, normalized with
                ``force_default_union=True``.
            data_graph: An optional default data graph, bound once here
                the same way ``shacl_graph``/``ont_graph`` already are, so
                a caller performing several different operations
                (``validate()``, ``apply_rules()``, ``evaluate()``, ...)
                against the same data doesn't have to keep re-passing it
                to every method call - each method's own ``data_graph``
                parameter is optional, falling back to this one (see
                ``_resolve_data_graph()``). Still fully overridable per
                call - binding a default here doesn't prevent passing a
                different ``data_graph`` to any one method.
            scoring_graph: An optional catalog of ``shui:WidgetScore``/
                ``shui:WidgetAcceptMatcher`` entries, bound once here the
                same way ``data_graph`` is. :meth:`select_widgets` uses it
                when called without its own ``scoring_graph=``; a per-call
                value overrides it. Only :meth:`select_widgets` reads it.
            inference: An optional entailment regime (one of the real
                ``ENTAILMENT.*`` IRIs, or an iterable of them), bound once
                here rather than accepted as a per-method keyword - an
                entailment regime is realistically a property of "how
                this schema interprets its data," not something a caller
                would want to vary call-to-call on the same schema.
                Methods below don't accept their own ``inference=``
                parameter at all - construct a second
                ``StarShaclSchema`` with a different ``inference=`` if
                two different regimes are genuinely needed against the
                same shapes/data.
            adapter: Overrides the ``TripleTermAdapter`` used to
                encode/decode triple terms around pySHACL. Defaults to a
                fresh ``TripleTermAdapter()``.
            validate_fn: Overrides the underlying ``(data_graph,
                shacl_graph, ont_graph, **options) -> (conforms,
                report_graph, report_text)`` callable ``validate()``
                dispatches to. Defaults to pySHACL's own ``validate()``.

        Note:
            There is deliberately no ``specification_graph=`` constructor
            parameter, unlike ``shacl_graph``/``ont_graph``/``inference``.
            Unlike those three, "what specification does this data
            conform to" isn't an intrinsic fact about how to validate -
            it's a publishing decision about what claim to make with a
            result, which can legitimately differ call to call even
            against the identical ``shacl_graph``. It stays what
            ``shacl_profiling.derive_conforms_to()``'s own
            ``specification_graph=`` was already designed for: an
            explicit, deliberate, application-level call after
            ``validate()`` returns - not something ``validate()``
            triggers automatically. ``sh:conformsTo`` (Profiling S5.5's
            first rule) is unaffected either way - it never depended on
            ``specification_graph``.
        """
        self.shacl_graph = (
            normalize_to_starlayer_graph(shacl_graph, name="shacl_graph") if shacl_graph is not None else None
        )
        self.ont_graph = (
            normalize_to_starlayer_graph(ont_graph, name="ont_graph", force_default_union=True)
            if ont_graph is not None
            else None
        )
        self.data_graph = (
            normalize_to_starlayer_graph(data_graph, name="data_graph") if data_graph is not None else None
        )
        self.scoring_graph = (
            normalize_to_starlayer_graph(scoring_graph, name="scoring_graph") if scoring_graph is not None else None
        )
        self.inference = inference
        self.adapter = adapter or TripleTermAdapter()
        self.validate_fn = validate_fn or _default_validate

    def _resolve_data_graph(self, data_graph: Any | None) -> Any:
        """Resolve the effective data graph for a processing method call:
        falls back to this instance's own bound ``self.data_graph`` when
        ``data_graph`` is omitted.

        Args:
            data_graph: The data graph explicitly passed to the calling
                method, or ``None`` to use the instance's bound default.

        Returns:
            The resolved data graph to operate on.

        Raises:
            ValueError: If both ``data_graph`` and ``self.data_graph`` are
                ``None`` - every downstream call expects a real graph.
        """
        resolved = data_graph if data_graph is not None else self.data_graph
        if resolved is None:
            raise ValueError(
                "No data_graph given, and this schema has no default data_graph "
                "bound at construction (StarShaclSchema(data_graph=...))."
            )
        return resolved

    def _resolve_shacl_graph(self, shapes_graph_resource: Any | None) -> Any | None:
        """Resolve the shapes graph for a processing method call that has
        no validation report to fall back to tagging.

        Every processing method's own shapes-graph input is
        ``self.shacl_graph`` by default; ``shapes_graph_resource=``, when
        given, instead resolves to one named ``sh:ShapesGraph`` module
        pulled out of it via :meth:`extract_shapes_graph`. Unlike
        :meth:`validate`'s own dual-purpose ``shapes_graph_resource=``
        (see :meth:`_resolve_shapes_graph_and_provenance`), a value that
        isn't really a module has nothing sensible left to mean here, so
        this still raises rather than silently doing something else.
        Never mutates or replaces ``self.shacl_graph`` itself - this is a
        call-local resolution only.

        Args:
            shapes_graph_resource: The IRI of a named ``sh:ShapesGraph``
                module within ``self.shacl_graph``, or ``None`` to use
                ``self.shacl_graph`` unchanged.

        Returns:
            The resolved shapes graph (``self.shacl_graph`` itself, the
            extracted module, or ``None``).

        Raises:
            ValueError: If ``shapes_graph_resource`` is given but
                ``self.shacl_graph`` is ``None``, or if the given IRI
                isn't typed ``a sh:ShapesGraph`` in it.
        """
        if shapes_graph_resource is None:
            return self.shacl_graph
        if self.shacl_graph is None:
            raise ValueError(
                "shapes_graph_resource= needs a bound shapes graph to extract from - "
                "construct with StarShaclSchema(shacl_graph=...)."
            )
        extracted = self.extract_shapes_graph(shapes_graph_resource)
        if extracted is None:
            raise ValueError(
                f"{shapes_graph_resource!r} is not typed `a sh:ShapesGraph` in this "
                "schema's own bound shacl_graph - extract_shapes_graph() returned None."
            )
        return extracted

    def _resolve_shapes_graph_and_provenance(self, shapes_graph_resource: Any | None) -> tuple[Any | None, Any | None]:
        """Resolve :meth:`validate`'s own dual-purpose
        ``shapes_graph_resource=``. One value, two possible meanings
        depending on what's actually true of this instance's own bound
        ``shacl_graph`` - not two independently-settable knobs that could
        disagree about which shapes graph was really used.

        - If ``shapes_graph_resource`` names a real ``a sh:ShapesGraph``
          module within the bound ``shacl_graph``: extract just that
          module (same as :meth:`_resolve_shacl_graph` would), and its
          own IRI becomes the report's ``sh:usedShapesGraph`` identity -
          there is only one real fact here ("which shapes graph was
          used"), so there is no second, separately-overridable value for
          it.
        - Otherwise (``self.shacl_graph`` is bound, but
          ``shapes_graph_resource`` genuinely isn't a module within it -
          typically because ``self.shacl_graph`` is the whole, anonymous
          graph being validated against as-is): validate against the
          whole bound ``shacl_graph`` unchanged, and use
          ``shapes_graph_resource`` purely as the report's
          ``sh:usedShapesGraph`` identity - for exactly the case this
          exists for (an anonymous graph that needs an
          externally-assigned identity). This positive check (a real
          graph exists and genuinely doesn't contain this resource as a
          module) is what makes "must be an external identity" a safe
          inference.
        - ``self.shacl_graph`` is ``None`` and ``shapes_graph_resource``
          is given: **raises**, same as :meth:`_resolve_shacl_graph` -
          with no bound graph at all, there's no evidence either way
          about what ``shapes_graph_resource`` means, and pyshacl
          trivially "conforms" against a ``None`` shapes graph - silently
          falling back to tag-only here would let the report claim
          ``sh:usedShapesGraph <shapes_graph_resource>`` for a
          validation run that checked nothing at all against it.
        - ``None``: no change, no provenance.

        One documented edge case: if a bare provenance IRI happens to
        coincide with a real ``sh:ShapesGraph`` node already in the bound
        graph, it's read as a module selector, not a plain tag - rare in
        practice, but a real consequence of collapsing two concepts into
        one value.

        Args:
            shapes_graph_resource: A named ``sh:ShapesGraph`` module's
                IRI, an arbitrary report-provenance identity, or
                ``None``.

        Returns:
            A ``(shacl_graph_to_validate_against,
            shapes_graph_iri_for_report)`` tuple.

        Raises:
            ValueError: If ``shapes_graph_resource`` is given but
                ``self.shacl_graph`` is ``None``.
        """
        if shapes_graph_resource is None:
            return self.shacl_graph, None
        if self.shacl_graph is None:
            raise ValueError(
                "shapes_graph_resource= needs a bound shapes graph to check against - "
                "construct with StarShaclSchema(shacl_graph=...). (If you only "
                "want to tag the report with an arbitrary identity, there's "
                "still nothing to validate against either way without a bound "
                "shacl_graph.)"
            )
        # Literal, not just URIRef, is preserved as-is - SHACL 1.2 Core
        # explicitly allows "the version IRI of a data/shapes graph" as a
        # value too, a Literal in the general case (see
        # _annotate_used_graphs_and_configuration's own identical
        # coercion). A Literal can never be a real sh:ShapesGraph module
        # (nothing it could equal as a triple subject), so it falls
        # through to the tag-only path below naturally either way.
        iri = shapes_graph_resource if isinstance(shapes_graph_resource, (URIRef, Literal)) else URIRef(str(shapes_graph_resource))
        extracted = self.extract_shapes_graph(iri)
        if extracted is not None:
            return extracted, iri
        return self.shacl_graph, iri

    def target_nodes(
        self,
        *,
        data_graph: Any | None = None,
        shape_node: Any,
        shapes_graph_resource: Any | None = None,
    ) -> tuple[Any, ...]:
        """Return the tuple of nodes this shape targets.

        ``data_graph`` is optional, falling back to ``self.data_graph``;
        ``inference`` is not a per-call parameter here - this instance's
        own bound ``self.inference`` is always used instead (see
        ``__init__``'s own docstring). Also threads this instance's own
        ``self.ont_graph`` through, matching every other method on this
        class - see ``engine.target_nodes()``'s own docstring for the
        full entailment design.

        Args:
            data_graph: The data graph to resolve targets against, or
                ``None`` to use ``self.data_graph``.
            shape_node: The shape whose targets to resolve.
            shapes_graph_resource: A named ``sh:ShapesGraph`` module's
                IRI to resolve ``shape_node`` within - see
                :meth:`_resolve_shacl_graph`.

        Returns:
            The tuple of target nodes.
        """
        data_graph = self._resolve_data_graph(data_graph)
        return native_target_nodes(
            data_graph=data_graph,
            shacl_graph=self._resolve_shacl_graph(shapes_graph_resource),
            shape_node=shape_node,
            ont_graph=self.ont_graph,
            inference=self.inference,
        )

    def evaluate_component(
        self,
        *,
        component: Any,
        focus_node: Any,
        value_nodes: tuple[Any, ...],
        options: dict[str, Any] | None = None,
    ) -> Any:
        """Evaluates one native ``ConstraintComponent`` directly against
        ``component``/``focus_node``/``value_nodes``.
        """
        request = ComponentRequest(
            component=component,
            focus_node=focus_node,
            value_nodes=value_nodes,
            options=options or {},
        )
        return native_evaluate_component(request)

    def build_report(
        self,
        *,
        events: tuple[dict[str, Any], ...],
        graph_context: Any,
        options: dict[str, Any] | None = None,
    ) -> Any:
        """Builds a ``sh:ValidationReport`` graph from component ``events``."""
        return native_build_report(events=events, graph_context=graph_context, options=options)

    def validate(
        self,
        data_graph: Any | None = None,
        *,
        mode: str | ValidationMode | None = None,
        decode_report: bool = True,
        rdfs_subclass_reasoning_includes_shapes_graph: bool = False,
        shapes_graph_loader: Callable[[Any], Any | None] | None = None,
        ignore_imports: bool = False,
        meta_shapes_extra: Iterable[Any] = (),
        data_graph_iri: Any | None = None,
        shapes_graph_resource: Any | None = None,
        include_used_configuration: bool = False,
        **kwargs: Any,
    ) -> ValidationResult:
        """Validate ``data_graph`` against this schema's bound
        ``shacl_graph``/``ont_graph``, with RDF 1.2/triple-term adaptation
        and the SHACL 1.2 Core/Node-Expressions/Profiling patches this
        module applies around pySHACL.

        Args:
            data_graph: The data graph to validate. Optional, falling
                back to ``self.data_graph`` (see ``__init__``'s own
                docstring) when omitted.
            mode: A validator option preset (``"validation"``/``"rules"``/
                ``"debug"``, or a ``ValidationMode``) resolved via
                ``resolve_mode_options()``; any of pySHACL's own options
                (e.g. ``advanced``, ``inplace``, ``meta_shacl``,
                ``allow_warnings``, ``allow_infos``) can be overridden
                through ``**kwargs``.
            decode_report: Whether to decode the raw pySHACL report graph
                back through the triple-term adapter (and humanize its
                report text) before returning it. ``False`` returns the
                adapter-encoded report as pySHACL produced it.
            rdfs_subclass_reasoning_includes_shapes_graph: Whether
                ``sh:rootClass``'s own ``rdfs:subClassOf`` reasoning
                should also consult the shapes graph's own
                ``rdfs:subClassOf`` triples, not just the data graph's -
                SHACL 1.2 Core's "SHACL Type" definition explicitly
                allows this to be implementation-parameterized. When
                enabled, the shapes graph's own ``rdfs:subClassOf``
                triples are injected into a copy of ``data_graph`` handed
                to pySHACL (the only channel available, since pySHACL
                constructs the ``sh:rootClass`` component itself with no
                room for extra constructor arguments) and removed again
                afterward.
            shapes_graph_loader: Resolves one ``owl:imports`` target IRI
                to the graph it names, or ``None`` if it can't be
                resolved - used to follow ``shacl_graph``'s own
                ``owl:imports`` (optionally redirected through
                ``owl:versionIRI``) before validating. This library
                never decides retrieval policy on its own, so no loader
                is used unless one is given.
            ignore_imports: If ``shacl_graph`` declares ``owl:imports``
                that aren't already locally satisfied (see
                ``has_import_locally()``) and no ``shapes_graph_loader``
                was given, ``validate()`` raises ``ValueError`` by
                default rather than silently proceeding with a possibly
                incomplete shapes graph. Pass ``True`` to opt out
                explicitly - e.g. because the imports were already
                resolved into ``shacl_graph`` beforehand (``resolve_imports()``
                doesn't strip the ``owl:imports`` triple once resolved,
                so its mere presence can't otherwise distinguish
                "already handled" from "genuinely missing").
            meta_shapes_extra: Extra graphs merged into the meta-shapes
                graph used for the ``meta_shacl=True`` preflight check
                (see ``starlayer.shacl.meta_shapes``). Ignored unless
                ``meta_shacl`` is enabled via ``mode``/``**kwargs``.
            data_graph_iri: The data graph's identity, recorded on the
                report as ``sh:usedDataGraph``. Falls back to
                ``data_graph.identifier`` when that's a real ``URIRef``
                (not the random ``BNode`` every plain ``rdflib.Graph``
                otherwise gets) and this is left ``None``.
            shapes_graph_resource: One value with two possible meanings,
                depending on what's actually true of this instance's own
                bound ``shacl_graph`` - see
                ``_resolve_shapes_graph_and_provenance()``'s own
                docstring for the full design. If it names a real
                ``a sh:ShapesGraph`` module within ``shacl_graph``, that
                module alone is validated against, and its own IRI
                becomes the report's ``sh:usedShapesGraph`` identity. If
                ``shacl_graph`` is bound but doesn't contain it as a
                module, it's used purely as the report's
                ``sh:usedShapesGraph`` identity, and the whole bound
                ``shacl_graph`` is validated against unchanged. Raises if
                given with no bound ``shacl_graph`` at all. Falls back to
                ``shacl_graph.identifier`` the same way ``data_graph_iri``
                falls back to ``data_graph.identifier``, when left
                ``None``.
            include_used_configuration: Whether to also record the
                resolved validator options (``mode``,
                ``rdfs_subclass_reasoning_includes_shapes_graph``, etc.)
                on the report.
            **kwargs: Forwarded into ``resolve_mode_options(mode,
                overrides=kwargs)`` as option overrides on top of
                whatever ``mode`` preset resolves to (e.g. ``advanced``,
                ``inplace``, ``meta_shacl``, ``allow_warnings``,
                ``allow_infos``). ``inference=`` is rejected with
                ``TypeError`` here - it's bound once at construction
                instead (``StarShaclSchema(inference=...)``); construct a
                second ``StarShaclSchema`` for a different regime.

        Returns:
            A ``ValidationResult`` with ``conforms``, ``report_graph``,
            ``report_text``, ``data_graph`` (the mutated data graph when
            ``inplace`` is enabled in the resolved options, else
            ``None``), and ``diagnostics``.
        """
        if "inference" in kwargs:
            raise TypeError(
                "validate() no longer accepts inference= directly - it's bound once at "
                "construction instead (StarShaclSchema(inference=...)). Construct a "
                "second StarShaclSchema if you need a different regime."
            )
        data_graph = self._resolve_data_graph(data_graph)

        self.adapter.reset_diagnostics()

        register_native_components()
        _patch_rdflib_data_graph_clone_preserves_tt_adapter()
        _patch_shape_value_nodes_for_sh_values()
        _patch_rules_apply_for_layer_and_run_once()
        _patch_stringify_for_native_backend_bnodes()

        options = resolve_mode_options(mode, overrides=kwargs)

        # See _resolve_shapes_graph_and_provenance()'s own docstring for
        # the full design of shapes_graph_resource's two possible
        # meanings, including the one documented edge case (an IRI that
        # coincidentally collides with a real module).
        shacl_graph_to_use, shapes_graph_iri = self._resolve_shapes_graph_and_provenance(shapes_graph_resource)

        data_graph, shacl_graph, ont_graph = normalize_graph_inputs(
            data_graph,
            shacl_graph_to_use,
            self.ont_graph,
        )

        # data_graph_iri falls back to the graph's own .identifier when
        # it's a real URIRef - never the default random BNode every
        # rdflib Graph otherwise gets, which carries no meaningful
        # identity to report. shapes_graph_iri gets the same fallback,
        # but only when shapes_graph_resource itself was never given at
        # all (resolved to None above) - an explicit shapes_graph_resource
        # of either kind is never overridden.
        if data_graph_iri is None and isinstance(data_graph.identifier, URIRef):
            data_graph_iri = data_graph.identifier
        if shapes_graph_iri is None and shacl_graph is not None and isinstance(shacl_graph.identifier, URIRef):
            shapes_graph_iri = shacl_graph.identifier

        ensure_graph_mutable(data_graph, name="data_graph")

        # SHACL 1.2 Core §1.4: a shapes graph's own sh:entailment
        # declaration(s) MUST be provided before/during validation -
        # applied here, once, up front, so every downstream step (target
        # resolution, constraint checking, shape-attached sh:rule
        # execution via the "rules" mode below) sees the same entailed
        # data graph uniformly. A no-op when shacl_graph declares no
        # sh:entailment and inference isn't given either (the common
        # case). inplace= is threaded through from the resolved mode
        # options, not hardcoded - the plain "validation" mode's own
        # documented never-mutate-the-caller's-data guarantee depends on
        # this. Reassign data_graph itself: when inplace=False this
        # returns a *new* graph, not the original. ont_graph is threaded
        # through too - entailment is *computed* over data_graph union
        # ont_graph (so an axiom declared only in ont_graph, the idiomatic
        # place for rdfs:domain/range/etc., is actually seen), but only
        # the newly-entailed delta is materialized - ont_graph's own raw
        # triples are never copied in, and ont_graph itself is never
        # mutated.
        #
        # inference comes from self.inference, bound once at construction
        # - not a per-call option (guarded above) - and shares
        # sh:entailment's own real ENTAILMENT.* IRI vocabulary directly,
        # rather than pySHACL's own ad-hoc string vocabulary - see
        # starlayer.shacl.entailment's own module docstring for the full
        # account.
        from starlayer.shacl.entailment import apply_entailment

        data_graph = apply_entailment(
            data_graph, shacl_graph, ont_graph, inplace=options.get("inplace", False), inference=self.inference
        )

        # sh:filterShape (SHACL-AF node expressions) is a confirmed pySHACL
        # bug, not merely "untested" as pySHACL's own source comment claims:
        # pyshacl/helper/expression_helper.py's filterShape handler calls
        # Shape.validate(data_graph, node) - a calling convention that
        # doesn't match what Shape.validate() actually expects in this
        # pySHACL version (it needs a SHACLExecutor first, not a raw data
        # graph), raising AttributeError: 'RdfLibDataGraph' object has no
        # attribute 'sparql_mode'. _patch_shape_validate_for_filter_shape
        # applies a small, backward-compatible compatibility shim (falls
        # through unchanged for every correctly-formed call) so this
        # actually works instead of crashing. If the patch can't be applied
        # (e.g. a pySHACL version whose internals no longer match what the
        # shim expects), fail fast with a clear message instead of letting
        # pySHACL's confusing internal crash surface to callers.
        if shacl_graph is not None and any(True for _ in shacl_graph.triples((None, SH.filterShape, None))):
            if not _patch_shape_validate_for_filter_shape():
                raise NotImplementedError(
                    "sh:filterShape is not supported: pySHACL's own implementation crashes "
                    "(AttributeError: 'RdfLibDataGraph' object has no attribute 'sparql_mode') "
                    "whenever it's actually used, confirmed with plain RDF 1.1 data, and "
                    "starShacl's compatibility workaround could not be applied against this "
                    "pySHACL version - see docs/upstream-issues/pyshacl-upstream-issues.md."
                )

        # SHACL 1.2 Node Expressions moved to the shnex: namespace
        # (https://www.w3.org/TR/shacl12-node-expr/); pySHACL 0.40.0 only
        # knows the old sh:union/sh:intersection/sh:filterShape/sh:path
        # forms. starlayer.shacl.node_expressions adds the 21 shnex:
        # operators and (via starlayer.shacl.sparql_node_expressions) the
        # sparql: namespace (SPARQL 1.1/1.2 built-in functions/operators as
        # node expressions) without touching pySHACL's own handling of the
        # old forms - see node_expressions.py's own docstring for the full
        # design. Checking for sparql:-namespaced predicates here too
        # (not just shnex:) matters on its own: a shapes graph using ONLY
        # sparql: node expressions, no shnex: ones at all, is entirely
        # legitimate (confirmed via the W3C SHACL 1.2 Node Expressions test
        # suite, which has fixtures doing exactly this), so both namespaces
        # must be checked to reach this patch through validate() itself.
        if shacl_graph is not None and any(
            True
            for p in shacl_graph.predicates()
            if str(p).startswith(str(SHNEX)) or str(p).startswith(str(SPARQL_EXPR_NS))
        ):
            from starlayer.shacl.node_expressions import (
                patch_node_expressions_for_shnex,
            )

            if not patch_node_expressions_for_shnex():
                raise NotImplementedError(
                    "shnex:/sparql: (SHACL 1.2 Node Expressions) predicates were found in "
                    "the shapes graph, but starShacl's support could not be wired into "
                    "this pySHACL version - see starlayer.shacl/node_expressions.py."
                )

        # sh:expression's own scope-seeding bug (see
        # _patch_expression_constraint_for_value_scope's docstring) affects
        # *any* sh:expression usage, not just shnex:/sparql:-tagged ones -
        # pySHACL's own call passes the value node where the real focus node
        # belongs, so even an old-form sh:this inside sh:expression is wrong
        # whenever focus != value (e.g. a property shape). Gated separately
        # from the shnex:/sparql: check above for exactly that reason.
        if shacl_graph is not None and any(True for _ in shacl_graph.triples((None, SH.expression, None))):
            if not _patch_expression_constraint_for_value_scope():
                raise NotImplementedError(
                    "sh:expression is not supported: pySHACL's own implementation passes the "
                    "wrong node as focusNode and never binds \"value\" in scope (see the SHACL "
                    "1.2 Node Expressions spec's sh:expression TEXTUAL DEFINITION), and "
                    "starShacl's fix could not be applied against this pySHACL version."
                )

        # SHACL 1.2 Core: a shapes graph can cross-reference reusable
        # modules via owl:imports (optionally redirected through
        # owl:versionIRI for versioned modules). This library doesn't
        # dictate a network-fetching policy, so retrieval is delegated to a
        # caller-supplied shapes_graph_loader.
        #
        # ignore_imports: if shacl_graph declares owl:imports that aren't
        # already locally satisfied (has_import_locally() - e.g. two
        # shapes-graph "modules" that import each other but have simply
        # been loaded together into one graph already, nothing external
        # to fetch at all) and no shapes_graph_loader was given, this
        # raises by default instead of silently proceeding with a
        # possibly-incomplete shapes graph - a shape referencing
        # something only defined in a
        # genuinely unresolved import would otherwise simply never fire,
        # with no indication anything was skipped. Pass
        # ignore_imports=True to opt out explicitly - e.g. because the
        # imports were already resolved into shacl_graph yourself
        # beforehand. That case is exactly why this can't *only* rely on
        # has_import_locally() instead of an explicit flag too:
        # resolve_imports() doesn't strip the owl:imports triple once
        # resolved via a loader (it's still a true fact about the
        # document), so its mere presence can't reliably distinguish
        # "already handled via a loader" from "genuinely missing" -
        # has_import_locally() only catches the *already-co-located*
        # case, not that one.
        if shacl_graph is not None and shapes_graph_loader is not None:
            shacl_graph = _resolve_shapes_graph_imports(shacl_graph, graph_loader=shapes_graph_loader)
        elif shacl_graph is not None and not ignore_imports:
            declared_imports = [o for o in shacl_graph.owl_imports() if not shacl_graph.has_import_locally(o)]
            if declared_imports:
                raise ValueError(
                    f"shacl_graph declares owl:imports {declared_imports!r} that aren't already "
                    "locally satisfied, but no shapes_graph_loader was given to resolve them. "
                    "Pass shapes_graph_loader=... to resolve them, or ignore_imports=True if "
                    "you've already resolved them yourself (or don't need them)."
                )

        # SHACL 1.2's new target types (sh:shape, implicit class targets via
        # rdfs:Class/sh:ShapeClass, sh:targetWhere) are unknown to pySHACL, so
        # a shape using only one of these would get zero targets from
        # pySHACL's perspective and silently "pass". Rather than another
        # native pass merged after the fact (which would only add violations,
        # not run the shape's *other* constraints), we pre-compute the extra
        # target nodes and inject them as ordinary sh:targetNode triples -
        # pySHACL already fully supports those, so every other constraint on
        # an affected shape validates correctly through the normal path too.
        shacl_graph = self._augment_shapes_with_new_target_types(data_graph, shacl_graph)

        # sh:deactivated [ shnex:.../sparql:... ]: a node expression computing
        # whether a shape is deactivated, rather than a plain boolean literal.
        # The node-expr spec's own "Getting Started" section only mentions
        # sh:deactivated in passing (no worked example, no evaluation
        # algorithm), but SHACL 1.2 *Core*'s "Deactivating Shapes and
        # Constraints" section (which node-expr defers basic SHACL
        # terminology to) gives the actual normative definition: "Let expr be
        # the value of sh:deactivated in a shape. If evalExpr(expr, data
        # graph, focus node, {}) produces true..." - evaluated once **per
        # focus node**, not once globally (a per-shape on/off switch would
        # be a genuinely different, wrong semantic for a per-target filter).
        #
        # pySHACL's own shape *loading* still hard-requires sh:deactivated's
        # value to be a Literal (ShapeLoadError), so the node-expression
        # triple is stripped from the shapes graph before pySHACL ever loads
        # shapes (same timing as the target-node fix above) and remembered in
        # a context-scoped registry; _patch_shape_focus_nodes_for_deactivated_expression
        # then filters each shape's own resolved focus nodes, evaluating the
        # expression once per candidate - the one pySHACL entrypoint that
        # sees "this shape's targets, before per-node constraint evaluation
        # begins" for the common (focus=None) validate() path.
        shacl_graph, deactivated_expr_registry = self._strip_deactivated_node_expressions(shacl_graph)

        # Predicates registered as real pySHACL constraint components (see
        # starlayer.shacl/native_components.py) whose value is itself a referenced
        # shape (e.g. sh:someValue) need that value explicitly typed
        # sh:NodeShape/sh:PropertyShape, or pySHACL's own shape-graph loader
        # won't recognize it as a shape at all (it only auto-discovers shapes
        # reachable via a fixed set of predicates - sh:property, sh:node,
        # sh:not, sh:qualifiedValueShape, sh:and/sh:or/sh:xone list members -
        # not the constraint-parameter registry itself).
        shacl_graph = self._ensure_native_component_shapes_typed(shacl_graph)

        # pySHACL's own meta_shacl=True mechanism has no extension point
        # (pyshacl/entrypoints.py::meta_validate always validates against
        # its own hardcoded, process-cached shacl-shacl.pickle - no
        # parameter to supply additional or replacement meta-shapes), so
        # it never learned about SHACL 1.2: 11 new predicates are silently
        # under-validated, and 8 shadowed predicates whose value space
        # SHACL 1.2 widened (list-valued sh:class/sh:datatype/sh:nodeKind,
        # path-valued sh:equals/sh:disjoint/sh:lessThan/
        # sh:lessThanOrEquals, sh:closed sh:ByTypes) are actively rejected
        # even though starlayer.shacl/native_components.py fully supports
        # them. starlayer.shacl.meta_shapes fully replaces pySHACL's own
        # mechanism (not supplements it -
        # running both would still reject the 8 widened forms via
        # pySHACL's unmodified check) with an assembled graph: pySHACL's
        # own base with those 8 now-too-strict triples removed, plus
        # starShacl's own SHACL 1.2 validation/presentation rules, plus
        # any caller-supplied meta_shapes_extra graphs.
        if shacl_graph is not None and options.get("meta_shacl"):
            from starlayer.shacl.meta_shapes import meta_validate

            # allow_warnings/allow_infos are forwarded so a caller who opts
            # into lenient data-conformance treatment for these severities
            # can equally opt into lenient meta-shacl preflight treatment
            # for the same severities - meta_validate calls plain
            # pyshacl.validate() directly (see its own docstring for why:
            # this preflight checks the caller's shacl_graph in the role of
            # *data*, against the meta-shapes graph in the role of
            # *shapes* - the inverse of validate()'s own main pass - so it
            # can't reuse validate()'s own shapes-graph-role-specific
            # pipeline, but it already forwards these two kwargs to pySHACL
            # correctly, so nothing else is needed here.
            meta_validate(
                shacl_graph,
                inference=options.get("inference"),
                extra_graphs=meta_shapes_extra,
                allow_warnings=options.get("allow_warnings"),
                allow_infos=options.get("allow_infos"),
            )
            # Structural meta-shacl above confirms every sh:select/sh:ask/
            # sh:construct is a well-formed xsd:string literal in the right
            # place - it never parses the string itself as SPARQL. This is
            # a separate, Python-level preflight for exactly that (see
            # meta_shapes.check_sparql_query_text's own docstring for why
            # it can't be a SHACL shape), gated by the same meta_shacl
            # opt-in/opt-out every other preflight check here already has.
            from starlayer.shacl.meta_shapes import check_sparql_query_text

            check_sparql_query_text(shacl_graph)
        options.pop("meta_shacl", None)

        # Every SHACL 1.2 predicate pySHACL doesn't natively implement is now
        # registered as a real pySHACL constraint component (see
        # starlayer.shacl/native_components.py, register_native_components() -
        # called above via StarShaclSchema.validate()'s own module import)
        # or handled by one of the other patterns in
        # docs/shacl12-gap-matrix.md's "Note on Architecture Direction" -
        # there's no longer a "known gap predicate" class to detect and
        # gate the native fast path or strip triples for.
        if _graph_contains_triple_terms(data_graph) or _graph_contains_triple_terms(
            shacl_graph
        ) or _graph_contains_triple_terms(ont_graph):
            native_result = self._try_native_core_validation(
                data_graph=data_graph,
                shacl_graph=shacl_graph,
                decode_report=decode_report,
            )
            if native_result is not None:
                return native_result

        shapes_for_pyshacl = shacl_graph

        # sh:rootClass (registered as a real pySHACL constraint component,
        # see starlayer.shacl/native_components.py) needs to consult the shapes
        # graph's own rdfs:subClassOf triples too when the caller opts into
        # that (rdfs_subclass_reasoning_includes_shapes_graph - the SHACL 1.2
        # Core spec's "SHACL Type" definition explicitly allows this to be
        # implementation-parameterized). Rather than threading that option
        # through to the component (which pySHACL constructs itself, with no
        # channel for extra constructor args), the shapes graph's own
        # rdfs:subClassOf triples are injected into the copy of data_graph
        # handed to pySHACL, so the component can query target_graph alone.
        data_for_pyshacl, injected_subclass_triples = _inject_shapes_graph_subclass_triples(
            data_graph,
            shacl_graph,
            enabled=rdfs_subclass_reasoning_includes_shapes_graph,
        )

        encoded_data = self.adapter.encode_graph(data_for_pyshacl)
        encoded_shapes = self.adapter.encode_graph(shapes_for_pyshacl) if shapes_for_pyshacl is not None else None
        encoded_ont = self.adapter.encode_graph(ont_graph) if ont_graph is not None else None

        deactivated_token = None
        if deactivated_expr_registry:
            if not _patch_shape_focus_nodes_for_deactivated_expression():
                raise NotImplementedError(
                    "sh:deactivated with a node-expression value is not supported: "
                    "starShacl's fix could not be applied against this pySHACL version - "
                    "see starlayer.shacl/validator.py::_patch_shape_focus_nodes_for_deactivated_expression."
                )
            deactivated_token = _deactivated_expr_registry.set(deactivated_expr_registry)
        try:
            conforms, report_graph, report_text = self.validate_fn(
                data_graph=encoded_data,
                shacl_graph=encoded_shapes,
                ont_graph=encoded_ont,
                **options,
            )
        finally:
            if deactivated_token is not None:
                _deactivated_expr_registry.reset(deactivated_token)

        # Confirmed pySHACL bug: a pyshacl.errors.ValidationFailure raised
        # deep inside constraint evaluation (e.g. a malformed custom
        # sh:ConstraintComponent SPARQL validator) is caught by pySHACL's
        # own top-level validate() and returned *as* report_graph, violating
        # its own documented (bool, Graph, str) return contract - report_text
        # is a real message in this case ("Validation Failure - ..."), but
        # report_graph is the exception object itself, not a Graph. Passing
        # that straight into decode_graph() below would crash with a
        # confusing, unrelated TypeError ('ValidationFailure' object is not
        # iterable) instead of surfacing the actual failure. Re-raise it
        # directly - it already carries pySHACL's own accurate message.
        if isinstance(report_graph, BaseException):
            raise report_graph

        for triple in injected_subclass_triples:
            encoded_data.remove(triple)

        out_report = self.adapter.decode_graph(report_graph) if decode_report else report_graph
        if decode_report:
            report_text = self._humanize_report_text(report_text)
        _rebuild_report_namespaces(
            out_report,
            specification_graph=None,
            data_graph=data_graph,
            shacl_graph=shacl_graph,
            ont_graph=ont_graph,
        )
        _relabel_validation_report_node(out_report)

        conforms = self._annotate_conformance_disallows(out_report, options, conforms)
        self._annotate_used_graphs_and_configuration(
            out_report,
            data_graph_iri=data_graph_iri,
            shapes_graph_iri=shapes_graph_iri,
            include_used_configuration=include_used_configuration,
        )
        # specification_graph=None - always: dcterms:conformsTo is no
        # longer auto-derived here (see __init__'s own comment for why) -
        # sh:conformsTo alone still fires unconditionally when both IRIs
        # resolve, since that rule has no specification_graph dependency.
        _merge_derived_conforms_to(out_report, data_graph_iri, shapes_graph_iri, None)
        report_text = _append_provenance_to_report_text(report_text, out_report, data_graph_iri)

        out_data: TripleTermGraph | Any | None = None
        if options.get("inplace"):
            if _is_starlayer_graph(data_graph):
                out_data = self.adapter.decode_graph(encoded_data)
                self.adapter.replace_graph(data_graph, out_data)
                out_data = data_graph
            else:
                self.adapter.replace_graph(data_graph, encoded_data)
                out_data = data_graph

        snapshot = self.adapter.diagnostics_snapshot()
        diagnostics = ExecutionDiagnostics(
            encode_graph_calls=snapshot["encode_graph_calls"],
            decode_graph_calls=snapshot["decode_graph_calls"],
            encoded_triple_terms=snapshot["encoded_triple_terms"],
            decoded_triple_terms=snapshot["decoded_triple_terms"],
            generated_support_triples=self.adapter.support_triple_count(),
            encoded_data_triples=len(encoded_data),
            report_triples=len(report_graph),
            inplace_data_triples=len(out_data) if out_data is not None else 0,
        )

        return ValidationResult(
            conforms=conforms,
            report_graph=out_report,
            report_text=report_text,
            data_graph=out_data,
            diagnostics=diagnostics,
        )

    def validate_each(
        self,
        data_graphs: Iterable[Any] | None = None,
        **kwargs: Any,
    ) -> dict[int, ValidationResult]:
        """Validate each of ``data_graphs`` independently against this
        instance's own bound ``shacl_graph``/``ont_graph``, mirroring
        pyshacl's own ``validate_each(data_graphs, ...)`` entry point.

        Implemented as a loop calling :meth:`validate` once per data graph,
        rather than driving pyshacl's own ``validate_each``/multi-data-graph
        path directly: that path knows nothing about RDF 1.2 triple terms,
        SHACL 1.2's new predicates, or any of this project's other runtime
        patches, so using it would silently run a different, unpatched
        pipeline per graph instead of the one real ``validate()`` path this
        class otherwise always goes through.

        Args:
            data_graphs: The data graphs to validate, each independently.
                ``None`` falls back to a single-element ``(self.data_graph,)``
                - :meth:`validate` itself raises if that is also ``None``, so
                no separate check is needed here.
            **kwargs: Forwarded verbatim to :meth:`validate` on every call
                (e.g. ``shapes_graph_resource``, ``mode``, ``inference``).

        Returns:
            A dict mapping each data graph's index in ``data_graphs`` to its
            own :class:`ValidationResult` - this project's own richer result
            type, not pyshacl's bare ``dict[int, (conforms, report_graph,
            report_text)]`` tuple, the same "wrap the tuple" convention
            :meth:`validate` itself already follows.
        """
        if data_graphs is None:
            data_graphs = (self.data_graph,)
        return {i: self.validate(data_graph, **kwargs) for i, data_graph in enumerate(data_graphs)}

    def _augment_shapes_with_new_target_types(self, data_graph: Any, shacl_graph: Any) -> Any:
        """Inject ``sh:targetNode`` triples for SHACL 1.2's new target types
        into a copy of ``shacl_graph``, so pySHACL's existing ``sh:targetNode``
        support picks them up (returns ``shacl_graph`` unchanged if none apply).
        """
        if shacl_graph is None:
            return shacl_graph

        additions: list[tuple[Any, Any, Any]] = []
        removals: list[tuple[Any, Any, Any]] = []

        # sh:targetNode [ sh:select "..." ]: a SPARQL-computed target node
        # set given directly as sh:targetNode's own value - a blank node
        # carrying sh:select, distinct from sh:targetWhere (whose value is a
        # whole shape, matched via conformance) and from pySHACL's own
        # existing sh:target [ sh:select ... ] (a *different* predicate,
        # already natively supported - SHACL-AF's SPARQLTarget). The
        # original (shape_node, sh:targetNode, blank_node) triple must be
        # removed, not just left alongside the computed ones: it uses the
        # exact same predicate pySHACL's native sh:targetNode support reads
        # directly as a target *node*, and a bare blank node carrying
        # sh:select is never itself a real target.
        for shape_node, _, target_value in shacl_graph.triples((None, SH.targetNode, None)):
            select_query = next(shacl_graph.objects(target_value, SH.select), None)
            if select_query is None:
                continue
            removals.append((shape_node, SH.targetNode, target_value))
            for row in data_graph.query(str(select_query)):
                additions.append((shape_node, SH.targetNode, row[0]))

        # sh:targetNode [ shnex:... ]/[ sparql:... ]: a node expression given
        # directly as sh:targetNode's own value, computing the shape's
        # target nodes dynamically - the SHACL 1.2 Node Expressions spec's
        # own opening ("Getting Started") example
        # (sh:targetNode [ shnex:nodes [ shnex:instancesOf ex:Company ] ;
        # shnex:filterShape [...] ]). pySHACL's own sh:targetNode support
        # treats *any* blank-node value as an opaque (bogus) target in its
        # own right, producing a nonsense "Focus Node" that's really just
        # the node expression's own blank node identity - a gap distinct
        # from the sh:select case above. Evaluated with no starting focus
        # node (matches the spec's own framing - "a node expression
        # produces the list of target nodes of a shape", not "...relative
        # to some other node"); every node expression the spec actually
        # demonstrates for this position (shnex:instancesOf,
        # shnex:nodesMatching, shnex:filterShape) is focus-node-independent
        # by construction, so this only matters for a shapes graph that (in
        # violation of the spec's own intent for this position) plugs in a
        # focus-dependent expression like a bare shnex:pathValues - which
        # then, correctly, produces no targets rather than a wrong guess.
        # Needs a real (harvested) pyshacl.ShapesGraph for the shnex:
        # operators that check shape conformance (shnex:filterShape/
        # nodesMatching/matchAll/findFirst/conformsToShape call
        # sg.lookup_shape_from_node(), which raises KeyError against an
        # unharvested one) - built once here and discarded; pySHACL's own
        # validate() call afterward builds its own fresh one from the
        # augmented shacl_graph produced by this method, so there's no
        # shared-state risk.
        #
        # Gated strictly on an actual shnex:/sparql: defining predicate -
        # NOT "any BNode without sh:select": sh:targetWhere resolution
        # (_nodes_conforming_to below) already stuffs arbitrary data-graph
        # blank nodes into sh:targetNode as plain candidate values,
        # completely unrelated to node expressions - one of them
        # coincidentally carrying sh:path (an ordinary nested property
        # shape's own path declaration, picked up because this fixture's
        # data graph and shapes graph are literally the same file) collides
        # with pySHACL's own *legacy* node-expression fallback (which
        # treats any sh:path-bearing blank node as a path expression),
        # producing a wrong extra target (W3C SHACL test suite's
        # targetWhere-001 fixture). The spec's own target-node worked
        # examples exclusively use shnex:-namespaced expressions, never the
        # ambiguous old sh:union/sh:path forms, so restricting this to real
        # shnex:/sparql: predicates is both spec-faithful and sidesteps the
        # ambiguity entirely.
        from starlayer.shacl.node_expressions import _is_shnex_expr
        from starlayer.shacl.sparql_node_expressions import is_sparql_expr

        _raw_sg = _RawGraphView(shacl_graph)
        target_expr_candidates = [
            (shape_node, target_value)
            for shape_node, _, target_value in shacl_graph.triples((None, SH.targetNode, None))
            if isinstance(target_value, BNode)
            and next(shacl_graph.objects(target_value, SH.select), None) is None
            and (_is_shnex_expr(_raw_sg, target_value) or is_sparql_expr(_raw_sg, target_value))
        ]
        if target_expr_candidates:
            from pyshacl.shapes_graph import ShapesGraph

            from starlayer.shacl.node_expressions import eval_expr

            throwaway_sg = ShapesGraph(shacl_graph)
            throwaway_sg.shapes  # noqa: B018 - property getter triggers shape-cache harvest

            for shape_node, target_value in target_expr_candidates:
                try:
                    computed = eval_expr(target_value, None, data_graph, throwaway_sg)
                except Exception:
                    continue
                # Remove the original blank-node triple even when computed is
                # empty - a node expression legitimately producing zero
                # target nodes means the shape targets nothing, which must
                # not fall back to pySHACL treating the raw blank node
                # itself as a (bogus) target.
                removals.append((shape_node, SH.targetNode, target_value))
                for node in computed:
                    additions.append((shape_node, SH.targetNode, node))

        # sh:shape - declared in the DATA graph (unlike sh:targetNode, which
        # is a shapes-graph triple): n sh:shape s means n is a target for s.
        for node, _, shape_node in data_graph.triples((None, SH.shape, None)):
            additions.append((shape_node, SH.targetNode, node))

        # Implicit class targets / sh:ShapeClass: a shape that is itself
        # declared rdfs:Class (or the sh:ShapeClass shortcut) targets its own
        # data-graph instances, *including* instances of rdfs:subClassOf
        # descendants of that class (per the SHACL Core spec's own implicit-
        # class-target definition - a shape declared on a class applies to
        # every subclass's instances too, the same way sh:targetClass does).
        # Candidate shape_nodes are the union of nodes typed sh:NodeShape,
        # rdfs:Class, or sh:ShapeClass - not just sh:NodeShape - since
        # rdfs:Class/sh:ShapeClass is meant as a standalone "shortcut" typing
        # per the spec's own framing, not one that additionally requires
        # explicit sh:NodeShape typing too (confirmed via the W3C SHACL 1.2
        # test suite's targetClassImplicit-002 fixture, whose sh:ShapeClass
        # node carries no separate sh:NodeShape type at all).
        implicit_class_candidates: set = set()
        for shape_node, _, _ in shacl_graph.triples((None, RDF.type, SH.NodeShape)):
            implicit_class_candidates.add(shape_node)
        for shape_node, _, _ in shacl_graph.triples((None, RDF.type, RDFS.Class)):
            implicit_class_candidates.add(shape_node)
        for shape_node, _, _ in shacl_graph.triples((None, RDF.type, SH.ShapeClass)):
            implicit_class_candidates.add(shape_node)
        for shape_node in implicit_class_candidates:
            if _is_implicit_class_shape(shacl_graph, shape_node):
                classes = {shape_node} | _transitive_subclasses(data_graph, shacl_graph, shape_node)
                for cls in classes:
                    for instance, _, _ in data_graph.triples((None, RDF.type, cls)):
                        additions.append((shape_node, SH.targetNode, instance))

                # pySHACL's own rule loader (pyshacl.rules.gather_rules) calls
                # shacl_graph.lookup_shape_from_node(sub) for every sh:rule
                # subject and hard-errors (RuleLoadError) if that node isn't
                # recognized as a shape - and it only recognizes sh:NodeShape/
                # sh:PropertyShape typing, not sh:ShapeClass/rdfs:Class on
                # their own, even though this codebase's own implicit-class-
                # target handling above treats them as valid standalone shape
                # typing. Confirmed via the W3C SHACL 1.2 test suite's
                # run-once-example fixture (`ex:Person a sh:ShapeClass ;
                # sh:rule ex:IteratingRule ...`) - RuleLoadError without this.
                # Adding sh:NodeShape is safe: _is_implicit_class_shape above
                # already treats sh:NodeShape+sh:ShapeClass together as a
                # normal combination (one of implicit_class_candidates' own
                # three type-sources), not something the rest of this file's
                # logic assumes is mutually exclusive with sh:ShapeClass.
                if any(True for _ in shacl_graph.triples((shape_node, SH.rule, None))):
                    additions.append((shape_node, RDF.type, SH.NodeShape))

        # sh:targetWhere: the target set is every data-graph node that
        # conforms to the given (usually inline) shape.
        for shape_node, _, where_shape in shacl_graph.triples((None, SH.targetWhere, None)):
            for node in self._nodes_conforming_to(data_graph, shacl_graph, shape_node, where_shape):
                additions.append((shape_node, SH.targetNode, node))

        if not additions and not removals:
            return shacl_graph

        removals_set = set(removals)
        augmented = type(shacl_graph)()
        for triple in shacl_graph:
            if triple in removals_set:
                continue
            augmented.add(triple)
        for triple in additions:
            augmented.add(triple)
        return augmented

    def _strip_deactivated_node_expressions(self, shacl_graph: Any) -> tuple[Any, dict[Any, Any]]:
        """Remove every ``sh:deactivated [ shnex:.../sparql:... ]`` triple
        from a copy of ``shacl_graph`` (pySHACL's own shape *loading* hard-
        requires a Literal here and crashes otherwise).

        The caller threads the returned registry into
        ``_deactivated_expr_registry`` around the actual pySHACL call, for
        ``_patch_shape_focus_nodes_for_deactivated_expression`` to evaluate
        per focus node - see that function and the call site's own comment
        for the full reasoning and spec citation (SHACL 1.2 Core's
        "Deactivating Shapes and Constraints" section).

        Args:
            shacl_graph: The shapes graph to strip, or ``None``.

        Returns:
            A ``(graph, registry)`` pair: ``graph`` is a stripped copy of
            ``shacl_graph`` with every node-expression-valued
            ``sh:deactivated`` triple removed, and ``registry`` maps each
            affected shape node to its original node-expression value.
            Returns ``(shacl_graph, {})`` unchanged (same object, empty
            dict) if ``shacl_graph`` is ``None`` or no such expression is
            present.
        """
        if shacl_graph is None:
            return shacl_graph, {}

        from starlayer.shacl.node_expressions import _is_shnex_expr
        from starlayer.shacl.sparql_node_expressions import is_sparql_expr

        raw_sg = _RawGraphView(shacl_graph)
        candidates = [
            (shape_node, target_value)
            for shape_node, _, target_value in shacl_graph.triples((None, SH.deactivated, None))
            if isinstance(target_value, BNode)
        ]
        candidates = [
            (shape_node, target_value)
            for shape_node, target_value in candidates
            if _is_shnex_expr(raw_sg, target_value) or is_sparql_expr(raw_sg, target_value)
        ]
        if not candidates:
            return shacl_graph, {}

        registry = {shape_node: target_value for shape_node, target_value in candidates}
        candidate_triples = {(s, SH.deactivated, v) for s, v in candidates}
        stripped = type(shacl_graph)()
        for triple in shacl_graph:
            if triple not in candidate_triples:
                stripped.add(triple)
        return stripped, registry

    def _ensure_native_component_shapes_typed(self, shacl_graph: Any) -> Any:
        """Type the values of shape-expecting native-component predicates
        (see ``starlayer.shacl.native_components.SHAPE_EXPECTING_PREDICATES``) as
        ``sh:NodeShape``/``sh:PropertyShape`` in a copy of ``shacl_graph``,
        so pySHACL's shape-graph loader recognizes them (returns
        ``shacl_graph`` unchanged if none apply).
        """
        if shacl_graph is None:
            return shacl_graph

        additions: list[tuple[Any, Any, Any]] = []
        for predicate in SHAPE_EXPECTING_PREDICATES:
            for _, _, value in shacl_graph.triples((None, predicate, None)):
                for shape_node in shape_reference_nodes(shacl_graph, value):
                    addition = ensure_shape_typed(shacl_graph, shape_node)
                    if addition is not None:
                        additions.append(addition)

        if not additions:
            return shacl_graph

        augmented = type(shacl_graph)()
        for triple in shacl_graph:
            augmented.add(triple)
        for triple in additions:
            augmented.add(triple)
        return augmented

    def _nodes_conforming_to(
        self,
        data_graph: Any,
        shacl_graph: Any,
        shape_node: Any,
        where_shape: Any,
    ) -> list[Any]:
        """Every non-literal node in ``data_graph`` that conforms to
        ``where_shape``, for ``sh:targetWhere``.

        Runs one batched nested ``validate()`` call (candidates as
        ``sh:targetNode`` on ``where_shape``) rather than one call per
        candidate. Excludes the triggering ``(shape_node, sh:targetWhere,
        where_shape)`` triple from the copy used for that nested call, or
        it would re-trigger this exact check on itself forever.

        Args:
            data_graph: The data graph candidates are drawn from.
            shacl_graph: The shapes graph ``where_shape`` is defined in.
            shape_node: The shape declaring ``sh:targetWhere where_shape``
                - excluded from the nested validation copy so the check
                doesn't recurse on itself.
            where_shape: The shape every candidate must conform to.

        Returns:
            Every non-literal node in ``data_graph`` that conforms to
            ``where_shape``.
        """
        candidates: set[Any] = set()
        for s, _, o in data_graph:
            if isinstance(s, (URIRef, BNode)):
                candidates.add(s)
            if isinstance(o, (URIRef, BNode)):
                candidates.add(o)

        if not candidates:
            return []

        augmented = type(shacl_graph)()
        for s, p, o in shacl_graph:
            if s == shape_node and p == SH.targetWhere and o == where_shape:
                continue
            augmented.add((s, p, o))
        for candidate in candidates:
            augmented.add((where_shape, SH.targetNode, candidate))

        fresh_validator = StarShaclSchema(shacl_graph=augmented)
        result = fresh_validator.validate(data_graph=data_graph, meta_shacl=False)

        # Only genuine top-level results (reachable from the report node's
        # own sh:result) count as "violating" - not every sh:focusNode
        # triple anywhere in the (decoded) report graph. A candidate that
        # fails one of where_shape's constraints can have some *other*,
        # unrelated data-graph node reported as that violation's sh:value;
        # if that value node happens to itself carry a pre-existing
        # sh:focusNode triple as part of its own data content (confirmed via
        # the W3C SHACL 1.2 test suite's targetWhere-001 fixture, whose
        # self-describing mf:result expected-validation-report block is
        # ordinary data here, since sht:dataGraph <> loads the whole
        # document) - pySHACL's own report-graph cloning copies that
        # incidental triple along with the value node, which a blanket
        # "any sh:focusNode object" scan wrongly counts as a violation
        # against an unrelated candidate.
        report_node = _find_genuine_report_node(result.report_graph)
        violating: set[Any] = set()
        if report_node is not None:
            for _, _, result_node in result.report_graph.triples((report_node, SH.result, None)):
                violating.update(o for _, _, o in result.report_graph.triples((result_node, SH.focusNode, None)))
        return [c for c in candidates if c not in violating]

    def _try_native_literal_only_validation(
        self,
        *,
        data_graph: Any,
        shacl_graph: Any | None,
        decode_report: bool,
    ) -> ValidationResult | None:
        if shacl_graph is None:
            return None

        data = normalize_graph_inputs(data_graph, None, None)[0]
        shapes = normalize_graph_inputs(shacl_graph, None, None)[0]

        node_shapes = tuple(s for s, _, _ in shapes.triples((None, RDF.type, SH.NodeShape)))
        if not node_shapes:
            return None

        events: list[dict[str, Any]] = []

        for shape in node_shapes:
            if any(True for _ in shapes.triples((shape, SH.rule, None))):
                return None

            props = tuple(o for _, _, o in shapes.triples((shape, SH.property, None)))
            if not props:
                return None

            focus_nodes = self.target_nodes(data_graph=data, shape_node=shape)

            for prop in props:
                path = next((o for _, _, o in shapes.triples((prop, SH.path, None))), None)
                if path is None:
                    return None

                if any(True for _ in shapes.triples((prop, SH.or_, None))):
                    return None

                component_name = self._resolve_literal_only_component_name(shapes, prop)
                if component_name is None:
                    return None

                source_component = _LITERAL_ONLY_COMPONENTS[component_name]

                for focus in focus_nodes:
                    values = tuple(o for _, _, o in data.triples((focus, path, None)))
                    if not values:
                        continue

                    if any(isinstance(v, Literal) for v in values):
                        return None

                    result = self.evaluate_component(
                        component={"name": component_name},
                        focus_node=focus,
                        value_nodes=values,
                    )
                    if result.conforms:
                        continue

                    for violation in result.violations:
                        events.append(
                            {
                                "focus_node": focus,
                                "result_path": path,
                                "value": violation,
                                "source_constraint_component": source_component,
                            }
                        )

        report_context = Graph() if decode_report else Graph()
        report = self.build_report(events=tuple(events), graph_context=report_context)
        diagnostics = ExecutionDiagnostics(report_triples=len(report))
        return ValidationResult(
            conforms=len(events) == 0,
            report_graph=report,
            report_text="native literal-only preflight",
            data_graph=None,
            diagnostics=diagnostics,
        )

    def _annotate_conformance_disallows(self, report_graph: Any, options: dict[str, Any], conforms: bool) -> bool:
        """Add ``sh:conformanceDisallows`` to the report per the SHACL 1.2
        Core spec: the set of severities whose presence makes ``sh:conforms``
        false. pySHACL's own ``allow_warnings``/``allow_infos`` options
        already implement the underlying behavior for ``sh:Violation``/
        ``sh:Warning``/``sh:Info`` (confirmed directly: a Warning- or
        Info-only result already flips ``sh:conforms`` to false by default,
        matching the spec's stated default disallow set of
        Violation+Warning+Info) - annotating ``disallowed`` just makes that
        set explicit in the report.

        Also recomputes ``sh:conforms`` itself (returned, and fixed up in
        ``report_graph`` to match) rather than trusting pySHACL's own
        boolean as-is: pySHACL has no notion of SHACL 1.2's new
        ``sh:Debug``/``sh:Trace`` severities (below ``sh:Warning``, must
        never block conformance regardless of ``allow_warnings``/
        ``allow_infos``) at all, so a shape using one of them still
        incorrectly flips ``sh:conforms`` to false. Recomputing purely from
        ``disallowed`` (rather than special-casing Debug/Trace separately)
        fixes this for free, since neither is ever a member of it - only
        ``sh:Violation``, and conditionally ``sh:Warning``/``sh:Info``, ever
        are. Confirmed via the W3C SHACL 1.2 test suite's severity-004/
        severity-005 fixtures.

        Args:
            report_graph: The validation report graph to annotate in place.
            options: The resolved validator options for this run - reads
                ``allow_warnings``/``allow_infos``.
            conforms: pySHACL's own computed conformance boolean, used as
                the fallback return value when no report node is found.

        Returns:
            The recomputed ``sh:conforms`` value (also written back onto
            ``report_graph``), or ``conforms`` unchanged if ``report_graph``
            has no ``sh:ValidationReport`` node at all.
        """
        report_node = _find_genuine_report_node(report_graph)
        if report_node is None:
            return conforms

        disallowed = {SH.Violation}
        if not options.get("allow_warnings"):
            disallowed.add(SH.Warning)
        if not options.get("allow_infos"):
            disallowed.add(SH.Info)

        report_graph.remove((report_node, SH.conformanceDisallows, None))
        for severity in disallowed:
            report_graph.add((report_node, SH.conformanceDisallows, severity))

        blocking = any(
            set(report_graph.objects(result_node, SH.resultSeverity)) & disallowed
            for _, _, result_node in report_graph.triples((report_node, SH.result, None))
        )
        new_conforms = not blocking
        report_graph.remove((report_node, SH.conforms, None))
        report_graph.add((report_node, SH.conforms, Literal(new_conforms)))
        return new_conforms

    def _annotate_used_graphs_and_configuration(
        self,
        report_graph: Any,
        *,
        data_graph_iri: Any | None,
        shapes_graph_iri: Any | None,
        include_used_configuration: bool,
    ) -> None:
        """Add ``sh:usedDataGraph``/``sh:usedShapesGraph``/``sh:usedConfiguration``
        to the report per SHACL 1.2 Core section 6.7.1.5-6.7.1.8 (added to
        the published spec 2026-08-03 - see docs/shacl12-gap-matrix.md's
        Core changelog table). All three are optional (``MAY``) provenance
        metadata; the spec is explicit that "SHACL processors MUST NOT
        alter their validation behavior based on the contents of a
        ``sh:ProcessorConfiguration`` instance" - added here purely
        additively, never read back by anything in this codebase.

        ``data_graph_iri``/``shapes_graph_iri`` are caller-supplied because
        an anonymous in-memory ``rdflib.Graph`` has no IRI identity of its
        own to report - the same "needs the caller to have already minted
        identity" situation already documented for SHACL 1.2 Profiling's
        ``sh:conformsTo`` inference rule (see this file's "Not Covered /
        Deferred" table). No default/invented IRI is generated when the
        caller omits one - a bare string is coerced to ``URIRef``, an
        already-a-term value (``URIRef``, or a ``Literal`` for a versioned
        graph IRI, which the spec explicitly allows) is used as-is.

        ``sh:usedConfiguration``/``sh:ProcessorConfiguration`` is opt-in
        (``include_used_configuration``, default ``False``): the spec
        leaves every property of ``sh:ProcessorConfiguration`` undefined
        ("Implementations are free to define whatever properties they
        need"), so with nothing concrete to say about a given run, adding
        an empty blank node to *every* report by default would be pure
        noise - only add the marker when a caller actually asks for it.

        Args:
            report_graph: The validation report graph to annotate in place.
            data_graph_iri: The data graph's own IRI/versioned-graph
                ``Literal``, or ``None`` to omit ``sh:usedDataGraph``.
            shapes_graph_iri: The shapes graph's own IRI/versioned-graph
                ``Literal``, or ``None`` to omit ``sh:usedShapesGraph``.
            include_used_configuration: Whether to add an (empty)
                ``sh:usedConfiguration``/``sh:ProcessorConfiguration``
                marker node.

        Returns:
            None - ``report_graph`` is mutated in place.
        """
        report_node = _find_genuine_report_node(report_graph)
        if report_node is None:
            return

        if data_graph_iri is not None:
            value = data_graph_iri if isinstance(data_graph_iri, (URIRef, Literal)) else URIRef(str(data_graph_iri))
            report_graph.add((report_node, SH.usedDataGraph, value))
        if shapes_graph_iri is not None:
            value = (
                shapes_graph_iri
                if isinstance(shapes_graph_iri, (URIRef, Literal))
                else URIRef(str(shapes_graph_iri))
            )
            report_graph.add((report_node, SH.usedShapesGraph, value))
        if include_used_configuration:
            config_node = BNode()
            report_graph.add((config_node, RDF.type, SH.ProcessorConfiguration))
            report_graph.add((report_node, SH.usedConfiguration, config_node))

    def _humanize_report_text(self, report_text: str) -> str:
        """Replace encoded triple-term URIs embedded in pySHACL's report text
        with a readable ``<<( s p o )>>`` rendering.

        pySHACL builds this text per-result before starShacl ever sees it, so
        unlike ``report_graph`` (which we decode via ``adapter.decode_graph``)
        there's no structured graph to decode - only string substitution
        against the adapter's own encoding registry. Applied repeatedly so
        nested triple terms (whose components are themselves encoded URIs)
        resolve fully.

        Args:
            report_text: pySHACL's own rendered report text, possibly
                containing encoded triple-term URIs.

        Returns:
            ``report_text`` with every encoded triple-term URI replaced by
            its readable ``<<( s p o )>>`` form, or unchanged if
            ``self.adapter``'s registry has no entries at all.
        """
        registry = self.adapter.export_registry()
        entries = registry.get("entries", [])
        if not entries:
            return report_text

        substitutions = {
            f"<{entry['uri']}>": f"<<( {entry['s']} {entry['p']} {entry['o']} )>>" for entry in entries
        }

        for _ in range(len(substitutions) + 1):
            changed = False
            for encoded, readable in substitutions.items():
                if encoded in report_text:
                    report_text = report_text.replace(encoded, readable)
                    changed = True
            if not changed:
                break

        return report_text

    def _try_native_core_validation(
        self,
        *,
        data_graph: Any,
        shacl_graph: Any | None,
        decode_report: bool,
    ) -> ValidationResult | None:
        literal_only = self._try_native_literal_only_validation(
            data_graph=data_graph,
            shacl_graph=shacl_graph,
            decode_report=decode_report,
        )
        if literal_only is not None:
            return literal_only

        structural = self._try_native_structural_property_validation(
            data_graph=data_graph,
            shacl_graph=shacl_graph,
            decode_report=decode_report,
        )
        if structural is not None:
            return structural

        return None

    def _resolve_literal_only_component_name(self, shapes: Any, prop: Any) -> str | None:
        present: list[str] = []
        for name in _LITERAL_ONLY_COMPONENTS:
            predicate = SH[name]
            if any(True for _ in shapes.triples((prop, predicate, None))):
                present.append(name)

        if len(present) != 1:
            return None
        return present[0]

    def _try_native_structural_property_validation(
        self,
        *,
        data_graph: Any,
        shacl_graph: Any | None,
        decode_report: bool,
    ) -> ValidationResult | None:
        if shacl_graph is None:
            return None

        data = normalize_graph_inputs(data_graph, None, None)[0]
        shapes = normalize_graph_inputs(shacl_graph, None, None)[0]

        node_shapes = tuple(s for s, _, _ in shapes.triples((None, RDF.type, SH.NodeShape)))
        if not node_shapes:
            return None

        events: list[dict[str, Any]] = []

        for shape in node_shapes:
            if any(True for _ in shapes.triples((shape, SH.rule, None))):
                return None

            props = tuple(o for _, _, o in shapes.triples((shape, SH.property, None)))
            if not props:
                return None

            focus_nodes = self.target_nodes(data_graph=data, shape_node=shape)

            for prop in props:
                path = next((o for _, _, o in shapes.triples((prop, SH.path, None))), None)
                if path is None:
                    return None

                structural = self._resolve_structural_component_definition(shapes, prop)
                if structural is None:
                    return None

                component_name, component_args = structural
                source_component = _STRUCTURAL_COMPONENTS[component_name]

                for focus in focus_nodes:
                    values = tuple(o for _, _, o in data.triples((focus, path, None)))
                    if not values:
                        continue

                    component = {"name": component_name}
                    component.update(component_args)
                    if component_name in {"equals", "disjoint"}:
                        other_path = component_args["other_path"]
                        component = {
                            "name": component_name,
                            "other_values": tuple(o for _, _, o in data.triples((focus, other_path, None))),
                        }

                    result = self.evaluate_component(
                        component=component,
                        focus_node=focus,
                        value_nodes=values,
                    )
                    if result.conforms:
                        continue

                    for violation in result.violations:
                        events.append(
                            {
                                "focus_node": focus,
                                "result_path": path,
                                "value": violation,
                                "source_constraint_component": source_component,
                            }
                        )

        report_context = Graph() if decode_report else Graph()
        report = self.build_report(events=tuple(events), graph_context=report_context)
        diagnostics = ExecutionDiagnostics(report_triples=len(report))
        return ValidationResult(
            conforms=len(events) == 0,
            report_graph=report,
            report_text="native structural-property preflight",
            data_graph=None,
            diagnostics=diagnostics,
        )

    def _resolve_structural_component_definition(self, shapes: Any, prop: Any) -> tuple[str, dict[str, Any]] | None:
        has_values = tuple(o for _, _, o in shapes.triples((prop, SH.hasValue, None)))
        in_values = tuple(o for _, _, o in shapes.triples((prop, SH["in"], None)))
        equals_values = tuple(o for _, _, o in shapes.triples((prop, SH.equals, None)))
        disjoint_values = tuple(o for _, _, o in shapes.triples((prop, SH.disjoint, None)))

        present = sum(bool(v) for v in (has_values, in_values, equals_values, disjoint_values))
        if present != 1:
            return None

        if has_values:
            if len(has_values) != 1:
                return None
            return "hasValue", {"value": has_values[0]}

        if in_values:
            if len(in_values) != 1:
                return None
            try:
                allowed = tuple(Collection(shapes, in_values[0]))
            except Exception:
                return None
            return "in", {"allowed": allowed}

        if equals_values:
            if len(equals_values) != 1:
                return None
            return "equals", {"other_path": equals_values[0]}

        if len(disjoint_values) != 1:
            return None
        return "disjoint", {"other_path": disjoint_values[0]}

    def apply_rules(
        self,
        data_graph: Any | None = None,
        include_source_rule_provenance: bool = False,
        rule_set: Any | None = None,
        shapes_graph_resource: Any | None = None,
        **kwargs: Any,
    ) -> RulesResult:
        """Executes SHACL rules against ``data_graph``, using this
        instance's own bound ``shacl_graph``/``ont_graph``.

        Delegates to the module-level :func:`apply_rules`, which holds
        the real implementation (mirroring pyshacl's own
        ``shacl_rules()`` entry point) - this method exists only to
        avoid repeating ``shacl_graph``/``ont_graph`` on every call.

        Args:
            data_graph: The data graph to run rules against. Optional -
                falls back to ``self.data_graph`` (see :meth:`__init__`)
                if omitted; raises ``ValueError`` if neither is given.
            include_source_rule_provenance: If ``True``, annotate each
                rule-produced triple with ``sh:sourceRule`` provenance
                pointing back at the rule that materialized it.
            rule_set: Optional ``sh:RuleSet`` node (or iterable of them)
                restricting which rule set(s) actually run, instead of
                every rule declared in the shapes graph.
            shapes_graph_resource: Selects a named ``sh:ShapesGraph``
                module within the bound ``shacl_graph`` to run rules
                against, or - if the bound ``shacl_graph`` doesn't
                contain it as a module - is used purely as
                report-provenance metadata. See
                :meth:`_resolve_shacl_graph`.
            **kwargs: Forwarded to the module-level :func:`apply_rules`.
                ``inference`` may not be passed here - it is always
                taken from ``self.inference``, bound at construction;
                passing it raises ``TypeError`` (Python's own "multiple
                values for keyword argument", since it is already
                supplied explicitly below).

        Returns:
            The ``RulesResult`` produced by the module-level
            :func:`apply_rules` call.
        """
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
    ) -> Any:
        """Computes every ``sh:values``-declared virtual property across
        ``shacl_graph`` and returns the result as a shape-driven subgraph.

        A third, independent processing mode alongside ``validate()``
        (checks conformance, never mutates) and ``apply_rules()``
        (executes ``sh:rule``, materializes real triples). Every focus
        node a property shape applies to gets its own real, stored
        ``sh:path`` values, plus any computed virtual values layered on
        top - never the whole of ``data_graph``. The caller's own
        ``data_graph`` is never mutated, and the returned graph is not
        meant to be persisted: SHACL 1.2 Node Expressions' own framing
        for virtual values is that they are computed "only on demand",
        never creating real triples in the data graph or shapes graph.

        This is a genuinely separate concern from ``apply_rules()``, not an
        overlapping one: a ``sh:values``-declared virtual property is
        invisible to ordinary node-expression path resolution
        (``shnex:pathValues``/pySHACL's own ``value_nodes_from_path``) the
        same way it's invisible to a plain ``sh:path`` read - a ``sh:rule``
        that tries to *read* a virtual property this way finds nothing, and
        only ever produces a real triple for that same computation if the
        rule *recomputes* it itself via the identical node expression.
        ``sh:values`` is wired only into ``Shape.value_nodes()`` (pySHACL's
        constraint-evaluation path, patched by
        ``_patch_shape_value_nodes_for_sh_values``), never into rule
        execution - so nothing here needs to coordinate with
        ``apply_rules()`` at all, or worry about double-materializing
        anything it already produces.

        Only handles a property shape's simple, single-predicate ``sh:path``
        (the form every worked example in the spec uses) - a property path
        expression (sequence/inverse/etc.) is silently skipped, matching
        this module's general "shallow but broad" tolerance elsewhere for
        forms not worth a full path-grammar evaluation here.

        **Unions with any real, already-stored value for the same
        predicate - does not remove or replace it.** SHACL 1.2 Core's own
        "Value Nodes of Property Shapes" algorithm is explicit and
        unambiguous about this: real path-based values and ``sh:values``-
        computed values are both unconditionally *added* to the same set
        (only ``sh:defaultValue`` is conditional, on the set still being
        empty) - see ``_patch_shape_value_nodes_for_sh_values``'s own
        docstring for the exact quoted algorithm. Every property shape with
        a real ``sh:path`` is visited for this, not only ones that also
        happen to declare ``sh:values``.

        **Entailment feeds the whole computation uniformly here** - unlike
        ``apply_rules()``, where entailment is a pure computational device
        that is never persisted into its returned inference graph, this
        method deliberately treats entailed triples as ordinary stored
        values: SHACL Core's own value-nodes algorithm makes no distinction
        between asserted and entailed triples, so neither does this method.

        ``self.shacl_graph is None`` (this schema was constructed with no
        shapes graph of its own) falls back to ``data_graph`` itself as the
        source of ``sh:values`` declarations - matching ``validate()``'s
        own "data graph doubles as shapes graph" allowance.

        Args:
            data_graph: The data graph to compute virtual values over.
                Optional - falls back to ``self.data_graph`` if omitted.
            shapes_graph_resource: Selects a named ``sh:ShapesGraph``
                module within the bound ``shacl_graph`` to read
                ``sh:values``/``sh:defaultValue`` declarations from, or is
                a no-op if the bound ``shacl_graph`` doesn't contain it as
                a module. See :meth:`_resolve_shacl_graph`. ``inference``
                is not a parameter here - it is always taken from
                ``self.inference``, bound at construction.

        Returns:
            A plain graph: the real, stored values of every property shape
            with a simple ``sh:path``, for its own target focus nodes, with
            any ``sh:values``/``sh:defaultValue``-computed values unioned
            in.
        """
        data_graph = self._resolve_data_graph(data_graph)
        shacl_graph_input = self._resolve_shacl_graph(shapes_graph_resource)
        data_graph, shacl_graph, ont_graph = normalize_graph_inputs(
            data_graph, shacl_graph_input if shacl_graph_input is not None else data_graph, self.ont_graph
        )

        from starlayer.shacl.entailment import apply_entailment

        data_graph = apply_entailment(data_graph, shacl_graph, ont_graph, inplace=False, inference=self.inference)

        shacl_graph = self._augment_shapes_with_new_target_types(data_graph, shacl_graph)

        from pyshacl.shapes_graph import ShapesGraph

        harvested_sg = ShapesGraph(shacl_graph)
        harvested_sg.shapes  # noqa: B018 - property getter triggers shape-cache harvest

        merged = type(data_graph)()
        for prefix, ns in data_graph.namespaces():
            merged.bind(prefix, ns)

        # Every property shape with a simple, single-predicate sh:path -
        # not just ones also declaring sh:values/sh:defaultValue -
        # contributes its real, stored triples for its own target focus
        # nodes. The returned graph is a shape-driven *subgraph* of
        # data_graph (only the parts the shapes graph actually describes
        # via a property path), not a full copy of data_graph - with
        # virtual sh:values/sh:defaultValue output layered on top of that
        # subgraph (2026-10-07: previously copied the whole of data_graph
        # up front and only the sh:values/sh:defaultValue-bearing shapes
        # were visited at all).
        all_prop_shapes = {s for s, _, _ in shacl_graph.triples((None, SH.path, None))}

        for prop_shape in all_prop_shapes:
            path_vals = list(shacl_graph.objects(prop_shape, SH.path))
            if len(path_vals) != 1 or not isinstance(path_vals[0], URIRef):
                continue
            predicate = path_vals[0]
            values_node = next(iter(shacl_graph.objects(prop_shape, SH.values)), None)
            default_values = list(shacl_graph.objects(prop_shape, SH.defaultValue))

            focus_nodes = set(_shape_target_nodes(data_graph, shacl_graph, prop_shape))
            for node_shape, _, _ in shacl_graph.triples((None, SH.property, prop_shape)):
                focus_nodes |= _shape_target_nodes(data_graph, shacl_graph, node_shape)
            if not focus_nodes:
                continue

            real_shape = None
            if values_node is not None:
                try:
                    real_shape = harvested_sg.lookup_shape_from_node(prop_shape)
                except KeyError:
                    real_shape = None

            for focus_node in focus_nodes:
                # Steps 1+2 (real path values, sh:values) are unconditionally
                # unioned - see this method's own docstring for the spec
                # citation. Step 3 (sh:defaultValue) only fires if that union
                # is still empty afterward - matching
                # _patch_shape_value_nodes_for_sh_values's identical
                # three-step algorithm on the validate() side, corrected
                # 2026-09-10 after a live check found evaluate() silently
                # ignored sh:defaultValue entirely (both for shapes that also
                # had sh:values and produced no output, and for the simpler
                # case of a property shape with only sh:defaultValue - the
                # original code only ever iterated sh:values triples, so a
                # defaultValue-only shape was never even visited).
                stored = list(data_graph.objects(focus_node, predicate))
                for value in stored:
                    merged.add((focus_node, predicate, value))

                computed = []
                if values_node is not None and real_shape is not None:
                    computed = _compute_sh_values(real_shape, values_node, data_graph, focus_node)
                    for value in computed:
                        merged.add((focus_node, predicate, value))
                if not stored and not computed and default_values:
                    for default_value_node in default_values:
                        for value in _compute_sh_default_value(default_value_node, data_graph, harvested_sg, focus_node):
                            merged.add((focus_node, predicate, value))

        return merged

    def select_widgets(
        self,
        *,
        shape_node: Any,
        focus_node: Any | None = None,
        role: str,
        data_graph: Any | None = None,
        scoring_graph: Any | None = None,
        shapes_graph_resource: Any | None = None,
    ) -> dict[Any, Any]:
        """Chooses a SHACL 1.2 UI widget for each property of the node
        shape ``shape_node``, using this instance's own bound
        ``shacl_graph`` as the shapes graph.

        Delegates to
        :func:`starlayer.shacl.ui_widget_selection.select_widgets`, which
        holds the real implementation and its full semantics - this method
        only supplies the bound shapes graph, the bound ``scoring_graph``
        and (when a ``focus_node`` is given) the bound ``data_graph``, so
        none of them is repeated per call. Each can be overridden per call.

        Args:
            shape_node: A ``sh:NodeShape`` in the shapes graph; its
                ``sh:property`` list is what is walked.
            focus_node: Optional node whose data a matcher's
                ``shui:dataGraphShape`` is checked against.
            role: ``"editor"`` or ``"viewer"``.
            data_graph: The graph holding ``focus_node``. Falls back to
                ``self.data_graph``; only needed (and only required) when
                ``focus_node`` is given.
            scoring_graph: Optional catalog of ``shui:WidgetScore`` /
                ``shui:WidgetAcceptMatcher`` entries. Falls back to
                ``self.scoring_graph``; to ignore a bound catalog for one
                call, pass an empty graph.
            shapes_graph_resource: Selects a named ``sh:ShapesGraph``
                module within the bound ``shacl_graph``, as for
                :meth:`apply_rules`.

        Returns:
            ``{property_shape: widget}``, with ``None`` for a property
            that has no widget.

        Raises:
            ValueError: If this schema has no ``shacl_graph``, or a
                ``focus_node`` is given with no data graph available.
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
        )

    def close_shape(self, shape: Any, *, shapes_graph_resource: Any | None = None) -> Any:
        """Returns a closed copy of ``shacl_graph``, closing ``shape`` and
        every shape it recursively references.

        ``shape`` is a node identifier already in this instance's own
        ``shacl_graph``. Every shape reached in a way that describes a
        value node's *complete* property set - ``sh:node``,
        ``sh:qualifiedValueShape``, every ``sh:and``/``sh:or``/``sh:xone``
        member - is closed (``sh:closed true``) with any
        ``sh:ignoredProperties`` stripped. The original ``shacl_graph`` is
        never mutated. See the module-level ``_close_shape`` in
        ``subgraph_extraction.py`` for the full algorithm/rationale -
        turning a shape's normal production form (which often tolerates a
        few properties via ``sh:ignoredProperties``) into the strict,
        no-exemptions form ``extract_subgraph()``'s acceptance test needs,
        without hand-maintaining a second, drift-prone copy of the shape.

        Unlike ``validate()``/``apply_rules()``/``evaluate()``, this
        doesn't take a ``data_graph`` at all - it operates purely on the
        bound ``shacl_graph`` itself.

        Args:
            shape: The shape node to close, already present in the bound
                ``shacl_graph``.
            shapes_graph_resource: Selects a named ``sh:ShapesGraph``
                module within the bound ``shacl_graph`` to close against,
                instead of the whole bound graph. See
                :meth:`_resolve_shacl_graph`.

        Returns:
            A closed copy of the relevant ``shacl_graph`` (or module).

        Raises:
            ValueError: If no shapes graph is bound at construction.
        """
        from starlayer.shacl.subgraph_extraction import _close_shape

        shacl_graph_input = self._resolve_shacl_graph(shapes_graph_resource)
        if shacl_graph_input is None:
            raise ValueError("close_shape() needs a bound shapes graph - construct with StarShaclSchema(shacl_graph=...).")
        return _close_shape(shacl_graph_input, shape)

    def extract_shapes_graph(self, shapes_graph_iri: Any) -> Any | None:
        """Extracts the ``sh:ShapesGraph``-typed resource named by
        ``shapes_graph_iri`` as a standalone graph.

        ``shapes_graph_iri`` must be declared within this instance's own
        bound ``shacl_graph``. The inverse of SHACL 1.2 Profiling §2's
        packaging convention: rather than reading a single shapes
        graph's own self-declared metadata, this pulls one *named*
        module back out of a larger graph that bundles several
        ``sh:ShapesGraph`` modules together side by side.

        A shape counts as a member of ``shapes_graph_iri``'s module via
        any of the three mechanisms SHACL 1.2 Profiling §2 documents,
        and all three are honored here:

        - ``<shapes_graph_iri> rdfs:member <Shape>`` - the ShapesGraph
          declares its own members (forward direction).
        - ``<Shape> rdfs:isDefinedBy <shapes_graph_iri>`` - a shape
          declares *itself* part of the ShapesGraph (inverse direction).
        - ``owl:imports`` - if ``shapes_graph_iri`` imports another
          ``sh:ShapesGraph`` node that's *already present in this same
          ``shacl_graph``*, that other module's own members (via either
          direction above) count as part of this module's result too,
          transitively. Only locally co-located modules are chased, the
          same "no implicit network/loader access" scope
          ``has_import_locally()``/``resolve_imports()`` already
          establish elsewhere - this method takes no ``loader=``
          parameter at all.

          **Unlike the dangling-member case below, an unresolvable
          ``owl:imports`` target raises ``ValueError`` rather than being
          silently skipped** - whether the imported IRI has no triples
          describing it in ``shacl_graph`` at all, or is present but
          simply isn't itself typed ``a sh:ShapesGraph``. A shapes graph
          that declares ``owl:imports`` on a ``sh:ShapesGraph`` node is
          asserting a real dependency on another packaging module, not
          offering optional metadata - call ``resolve_imports(loader=...)``
          on ``shacl_graph`` first if the target genuinely needs fetching
          from elsewhere before extracting.

        The result contains every involved ``sh:ShapesGraph`` node's own
        Concise Bounded Description (``StarLayerGraph.cbd()`` - its
        ``rdf:type sh:ShapesGraph``/``rdfs:member``/``owl:imports``
        triples, plus anything hanging off it via a blank node) **and**
        every member shape's own CBD too - CBD alone on a ShapesGraph
        node would include the bare ``rdfs:member`` triples themselves
        (each member is an ordinary named IRI, not a blank node, so CBD
        doesn't follow it further on its own) but not the member shapes'
        own content, which is why each one gets its own explicit CBD call
        here, the same way ``sh:property``'s own near-universally-blank-
        node shapes already come along for free via CBD's own blank-
        node-following behavior.

        Deliberately does **not** recurse into a member's own structural
        references (``sh:property``/``sh:node``/``sh:qualifiedValueShape``/
        etc.) to pull in whatever *named* shape they point at - only each
        direct member's own CBD. SHACL 1.2 Profiling itself gives no
        completeness rule here at all (§2.7, "Calculating Dependencies,"
        is a literal ``TODO`` in the published Working Draft; §2.3-2.5's
        ``rdfs:member``/``rdfs:isDefinedBy`` language is flat and
        non-transitive), so there's no spec basis for choosing a closure
        over this narrower scope. A member shape's own named structural
        reference is deliberately left dangling if its target isn't
        *itself* a direct member too - this lets a caller extract one
        shape, then inject their own (possibly different) definition for
        whatever it references, without the extraction silently dragging
        along a stale copy that would conflict with the injected one.
        If the caller wants a fully self-contained, ready-to-validate
        module instead, they're responsible for making sure every
        referenced named shape is also a declared member (or for
        injecting one themselves after extraction) - this method won't
        infer it on their behalf.

        Args:
            shapes_graph_iri: The IRI of the ``sh:ShapesGraph``-typed
                resource to extract.

        Returns:
            A standalone graph containing just that resource's module, or
            ``None`` if ``shapes_graph_iri`` isn't actually typed
            ``a sh:ShapesGraph`` in ``shacl_graph`` at all - not every
            graph bothers with this optional packaging metadata, and a
            typo'd IRI shouldn't silently return an
            empty-but-valid-looking graph.

        Raises:
            ValueError: If no shapes graph is bound at construction, or if
                an ``owl:imports`` target among ``sh:ShapesGraph`` nodes
                can't be resolved locally (see above).
        """
        if self.shacl_graph is None:
            raise ValueError(
                "extract_shapes_graph() needs a bound shapes graph - construct with "
                "StarShaclSchema(shacl_graph=...)."
            )
        sg = self.shacl_graph
        if (shapes_graph_iri, RDF.type, SH.ShapesGraph) not in sg:
            return None

        shapes_graph_nodes = {shapes_graph_iri}
        pending = [shapes_graph_iri]
        while pending:
            current = pending.pop()
            for imported in sg.objects(current, OWL.imports):
                if imported in shapes_graph_nodes:
                    continue
                if (imported, RDF.type, SH.ShapesGraph) not in sg:
                    raise ValueError(
                        f"{current!r} declares owl:imports {imported!r}, but {imported!r} "
                        "is not typed `a sh:ShapesGraph` in this schema's own bound "
                        "shacl_graph - either it has no triples describing it at all "
                        "(call resolve_imports(loader=...) on shacl_graph first if it "
                        "needs fetching from elsewhere), or it's present but isn't "
                        "itself a packaging module."
                    )
                shapes_graph_nodes.add(imported)
                pending.append(imported)

        result = type(sg)()
        for prefix, ns in sg.namespaces():
            result.bind(prefix, ns)

        members = set()
        for node in shapes_graph_nodes:
            for t in sg.cbd(node):
                result.add(t)
            members.update(sg.objects(node, RDFS.member))
            members.update(sg.subjects(RDFS.isDefinedBy, node))

        for member in members:
            for t in sg.cbd(member):
                result.add(t)
        return result


def _augment_shapes_with_new_target_types(data_graph: Any, shacl_graph: Any) -> Any:
    """Inject ``sh:targetNode`` triples for SHACL 1.2's new target types
    into a copy of ``shacl_graph``, so pySHACL's existing ``sh:targetNode``
    support picks them up (returns ``shacl_graph`` unchanged if none apply).

    Handles four distinct target mechanisms, each contributing its own
    ``(shape_node, sh:targetNode, node)`` triples: a ``sh:targetNode``
    value carrying ``sh:select`` (a SPARQL-computed node set, with the
    original blank-node triple removed, since a bare ``sh:select``-bearing
    blank node is never itself a real target); a ``sh:targetNode`` value
    that is a ``shnex:``/``sparql:`` node expression (evaluated via a
    throwaway, harvested ``pyshacl.ShapesGraph`` so ``shnex:filterShape``/
    ``nodesMatching``/etc. can check shape conformance - detection gates
    on a real ``shnex:``/``sparql:`` defining predicate, not "any blank
    node without ``sh:select``", to avoid colliding with pySHACL's own
    legacy ``sh:path``-bearing-blank-node fallback, confirmed against the
    W3C ``targetWhere-001`` fixture); data-graph ``sh:shape`` triples; and
    implicit class targets (a shape itself typed ``sh:NodeShape``/
    ``rdfs:Class``/``sh:ShapeClass`` targets its own data-graph instances,
    including instances of ``rdfs:subClassOf`` descendants - also adding
    ``sh:NodeShape`` typing when the shape carries ``sh:rule``, since
    pySHACL's own rule loader requires that typing to recognize the
    subject as a shape at all) and ``sh:targetWhere`` (delegates to
    ``_nodes_conforming_to``).
    """
    if shacl_graph is None:
        return shacl_graph

    additions: list[tuple[Any, Any, Any]] = []
    removals: list[tuple[Any, Any, Any]] = []

    # sh:targetNode [ sh:select "..." ]: a SPARQL-computed target node
    # set given directly as sh:targetNode's own value - a blank node
    # carrying sh:select, distinct from sh:targetWhere (whose value is a
    # whole shape, matched via conformance) and from pySHACL's own
    # existing sh:target [ sh:select ... ] (a *different* predicate,
    # already natively supported - SHACL-AF's SPARQLTarget). The
    # original (shape_node, sh:targetNode, blank_node) triple must be
    # removed, not just left alongside the computed ones: it uses the
    # exact same predicate pySHACL's native sh:targetNode support reads
    # directly as a target *node*, and a bare blank node carrying
    # sh:select is never itself a real target.
    for shape_node, _, target_value in shacl_graph.triples((None, SH.targetNode, None)):
        select_query = next(shacl_graph.objects(target_value, SH.select), None)
        if select_query is None:
            continue
        removals.append((shape_node, SH.targetNode, target_value))
        for row in data_graph.query(str(select_query)):
            additions.append((shape_node, SH.targetNode, row[0]))

    # sh:targetNode [ shnex:... ]/[ sparql:... ]: a node expression given
    # directly as sh:targetNode's own value, computing the shape's
    # target nodes dynamically - the SHACL 1.2 Node Expressions spec's
    # own opening ("Getting Started") example
    # (sh:targetNode [ shnex:nodes [ shnex:instancesOf ex:Company ] ;
    # shnex:filterShape [...] ]). Needs a real (harvested) pyshacl.ShapesGraph
    # for the shnex: operators that check shape conformance
    # (shnex:filterShape/nodesMatching/matchAll/findFirst/conformsToShape
    # call sg.lookup_shape_from_node(), which raises KeyError against an
    # unharvested one) - built once here and discarded; pySHACL's own
    # validate() call afterward builds its own fresh one from the
    # augmented shacl_graph produced by this function, so there's no
    # shared-state risk.
    #
    # Gated strictly on an actual shnex:/sparql: defining predicate -
    # NOT "any BNode without sh:select": sh:targetWhere resolution
    # (_nodes_conforming_to below) already stuffs arbitrary data-graph
    # blank nodes into sh:targetNode as plain candidate values,
    # completely unrelated to node expressions.
    from starlayer.shacl.node_expressions import _is_shnex_expr
    from starlayer.shacl.sparql_node_expressions import is_sparql_expr

    _raw_sg = _RawGraphView(shacl_graph)
    target_expr_candidates = [
        (shape_node, target_value)
        for shape_node, _, target_value in shacl_graph.triples((None, SH.targetNode, None))
        if isinstance(target_value, BNode)
        and next(shacl_graph.objects(target_value, SH.select), None) is None
        and (_is_shnex_expr(_raw_sg, target_value) or is_sparql_expr(_raw_sg, target_value))
    ]
    if target_expr_candidates:
        from pyshacl.shapes_graph import ShapesGraph

        from starlayer.shacl.node_expressions import eval_expr

        throwaway_sg = ShapesGraph(shacl_graph)
        throwaway_sg.shapes  # noqa: B018 - property getter triggers shape-cache harvest

        for shape_node, target_value in target_expr_candidates:
            try:
                computed = eval_expr(target_value, None, data_graph, throwaway_sg)
            except Exception:
                continue
            # Remove the original blank-node triple even when computed is
            # empty - a node expression legitimately producing zero
            # target nodes means the shape targets nothing, which must
            # not fall back to pySHACL treating the raw blank node
            # itself as a (bogus) target.
            removals.append((shape_node, SH.targetNode, target_value))
            for node in computed:
                additions.append((shape_node, SH.targetNode, node))

    # sh:shape - declared in the DATA graph (unlike sh:targetNode, which
    # is a shapes-graph triple): n sh:shape s means n is a target for s.
    for node, _, shape_node in data_graph.triples((None, SH.shape, None)):
        additions.append((shape_node, SH.targetNode, node))

    # Implicit class targets / sh:ShapeClass: a shape that is itself
    # declared rdfs:Class (or the sh:ShapeClass shortcut) targets its own
    # data-graph instances, *including* instances of rdfs:subClassOf
    # descendants of that class (per the SHACL Core spec's own implicit-
    # class-target definition). Candidate shape_nodes are the union of
    # nodes typed sh:NodeShape, rdfs:Class, or sh:ShapeClass.
    implicit_class_candidates: set = set()
    for shape_node, _, _ in shacl_graph.triples((None, RDF.type, SH.NodeShape)):
        implicit_class_candidates.add(shape_node)
    for shape_node, _, _ in shacl_graph.triples((None, RDF.type, RDFS.Class)):
        implicit_class_candidates.add(shape_node)
    for shape_node, _, _ in shacl_graph.triples((None, RDF.type, SH.ShapeClass)):
        implicit_class_candidates.add(shape_node)
    for shape_node in implicit_class_candidates:
        if _is_implicit_class_shape(shacl_graph, shape_node):
            classes = {shape_node} | _transitive_subclasses(data_graph, shacl_graph, shape_node)
            for cls in classes:
                for instance, _, _ in data_graph.triples((None, RDF.type, cls)):
                    additions.append((shape_node, SH.targetNode, instance))

            # pySHACL's own rule loader (pyshacl.rules.gather_rules) calls
            # shacl_graph.lookup_shape_from_node(sub) for every sh:rule
            # subject and hard-errors (RuleLoadError) if that node isn't
            # recognized as a shape - and it only recognizes sh:NodeShape/
            # sh:PropertyShape typing, not sh:ShapeClass/rdfs:Class on
            # their own. Adding sh:NodeShape is safe: _is_implicit_class_shape
            # above already treats sh:NodeShape+sh:ShapeClass together as a
            # normal combination.
            if any(True for _ in shacl_graph.triples((shape_node, SH.rule, None))):
                additions.append((shape_node, RDF.type, SH.NodeShape))

    # sh:targetWhere: the target set is every data-graph node that
    # conforms to the given (usually inline) shape.
    for shape_node, _, where_shape in shacl_graph.triples((None, SH.targetWhere, None)):
        for node in _nodes_conforming_to(data_graph, shacl_graph, shape_node, where_shape):
            additions.append((shape_node, SH.targetNode, node))

    if not additions and not removals:
        return shacl_graph

    removals_set = set(removals)
    augmented = type(shacl_graph)()
    for triple in shacl_graph:
        if triple in removals_set:
            continue
        augmented.add(triple)
    for triple in additions:
        augmented.add(triple)
    return augmented


def _strip_deactivated_node_expressions(shacl_graph: Any) -> tuple[Any, dict[Any, Any]]:
    """Remove every ``sh:deactivated [ shnex:.../sparql:... ]`` triple
    from a copy of ``shacl_graph`` (pySHACL's own shape *loading* hard-
    requires a Literal here and crashes otherwise), returning
    ``(graph, registry)`` where ``registry`` maps each affected shape
    node to its original node-expression value. The caller threads
    ``registry`` into ``_deactivated_expr_registry`` around the actual
    pySHACL call, for ``_patch_shape_focus_nodes_for_deactivated_expression``
    to evaluate per focus node.

    Returns ``(shacl_graph, {})`` unchanged if no such expression is
    present.
    """
    if shacl_graph is None:
        return shacl_graph, {}

    from starlayer.shacl.node_expressions import _is_shnex_expr
    from starlayer.shacl.sparql_node_expressions import is_sparql_expr

    raw_sg = _RawGraphView(shacl_graph)
    candidates = [
        (shape_node, target_value)
        for shape_node, _, target_value in shacl_graph.triples((None, SH.deactivated, None))
        if isinstance(target_value, BNode)
    ]
    candidates = [
        (shape_node, target_value)
        for shape_node, target_value in candidates
        if _is_shnex_expr(raw_sg, target_value) or is_sparql_expr(raw_sg, target_value)
    ]
    if not candidates:
        return shacl_graph, {}

    registry = {shape_node: target_value for shape_node, target_value in candidates}
    candidate_triples = {(s, SH.deactivated, v) for s, v in candidates}
    stripped = type(shacl_graph)()
    for triple in shacl_graph:
        if triple not in candidate_triples:
            stripped.add(triple)
    return stripped, registry


def _ensure_native_component_shapes_typed(shacl_graph: Any) -> Any:
    """Type the values of shape-expecting native-component predicates
    (see ``starlayer.shacl.native_components.SHAPE_EXPECTING_PREDICATES``) as
    ``sh:NodeShape``/``sh:PropertyShape`` in a copy of ``shacl_graph``,
    so pySHACL's shape-graph loader recognizes them (returns
    ``shacl_graph`` unchanged if none apply).
    """
    if shacl_graph is None:
        return shacl_graph

    additions: list[tuple[Any, Any, Any]] = []
    for predicate in SHAPE_EXPECTING_PREDICATES:
        for _, _, value in shacl_graph.triples((None, predicate, None)):
            for shape_node in shape_reference_nodes(shacl_graph, value):
                addition = ensure_shape_typed(shacl_graph, shape_node)
                if addition is not None:
                    additions.append(addition)

    if not additions:
        return shacl_graph

    augmented = type(shacl_graph)()
    for triple in shacl_graph:
        augmented.add(triple)
    for triple in additions:
        augmented.add(triple)
    return augmented


def _nodes_conforming_to(
    data_graph: Any,
    shacl_graph: Any,
    shape_node: Any,
    where_shape: Any,
) -> list[Any]:
    """Every non-literal node in ``data_graph`` that conforms to
    ``where_shape``, for ``sh:targetWhere``. Runs one batched nested
    ``validate()`` call (candidates as ``sh:targetNode`` on ``where_shape``)
    rather than one call per candidate. Excludes the triggering
    ``(shape_node, sh:targetWhere, where_shape)`` triple from the copy
    used for that nested call, or it would re-trigger this exact check on
    itself forever.

    Args:
        data_graph: The data graph to scan for non-literal candidate
            nodes (every subject/object that is a ``URIRef`` or ``BNode``).
        shacl_graph: The shapes graph ``where_shape`` is defined in.
        shape_node: The shape declaring ``sh:targetWhere where_shape``.
        where_shape: The shape every returned node must conform to.

    Returns:
        The candidate nodes that conform to ``where_shape``, found via
        the genuine top-level ``sh:result``/``sh:focusNode`` entries of
        the nested validation report (not any incidental ``sh:focusNode``
        triple that happens to appear elsewhere in the decoded report).
    """
    candidates: set[Any] = set()
    for s, _, o in data_graph:
        if isinstance(s, (URIRef, BNode)):
            candidates.add(s)
        if isinstance(o, (URIRef, BNode)):
            candidates.add(o)

    if not candidates:
        return []

    augmented = type(shacl_graph)()
    for s, p, o in shacl_graph:
        if s == shape_node and p == SH.targetWhere and o == where_shape:
            continue
        augmented.add((s, p, o))
    for candidate in candidates:
        augmented.add((where_shape, SH.targetNode, candidate))

    result = validate(data_graph, augmented, meta_shacl=False)

    # Only genuine top-level results (reachable from the report node's
    # own sh:result) count as "violating" - not every sh:focusNode
    # triple anywhere in the (decoded) report graph. A candidate that
    # fails one of where_shape's constraints can have some *other*,
    # unrelated data-graph node reported as that violation's sh:value;
    # if that value node happens to itself carry a pre-existing
    # sh:focusNode triple as part of its own data content, pySHACL's own
    # report-graph cloning copies that incidental triple along with the
    # value node, which a blanket "any sh:focusNode object" scan wrongly
    # counts as a violation against an unrelated candidate.
    report_node = _find_genuine_report_node(result.report_graph)
    violating: set[Any] = set()
    if report_node is not None:
        for _, _, result_node in result.report_graph.triples((report_node, SH.result, None)):
            violating.update(o for _, _, o in result.report_graph.triples((result_node, SH.focusNode, None)))
    return [c for c in candidates if c not in violating]


def _try_native_literal_only_validation(
    *,
    data_graph: Any,
    shacl_graph: Any | None,
    decode_report: bool,
) -> ValidationResult | None:
    """Attempt a fast, native-only validation path that bypasses pySHACL
    entirely, for the narrow case where ``shacl_graph`` consists only of
    node shapes whose property shapes each declare exactly one
    literal-only component (``sh:pattern``/``sh:datatype``/
    ``sh:languageIn``/``sh:minLength``/``sh:maxLength`` - see
    ``_LITERAL_ONLY_COMPONENTS``) and carry only ``Literal`` values.

    Returns ``None`` (meaning: fall back to full pySHACL validation)
    whenever ``shacl_graph`` is ``None``, there are no node shapes, any
    node shape has ``sh:rule``/no ``sh:property``, any property shape has
    no ``sh:path``/has ``sh:or``/declares zero or more than one
    literal-only component, or any focus node's values for a property's
    path include a non-``Literal`` term. Otherwise evaluates every
    literal-only component via ``native_evaluate_component`` and returns
    a ``ValidationResult`` built from the resulting violation events.
    """
    if shacl_graph is None:
        return None

    data = normalize_graph_inputs(data_graph, None, None)[0]
    shapes = normalize_graph_inputs(shacl_graph, None, None)[0]

    node_shapes = tuple(s for s, _, _ in shapes.triples((None, RDF.type, SH.NodeShape)))
    if not node_shapes:
        return None

    events: list[dict[str, Any]] = []

    for shape in node_shapes:
        if any(True for _ in shapes.triples((shape, SH.rule, None))):
            return None

        props = tuple(o for _, _, o in shapes.triples((shape, SH.property, None)))
        if not props:
            return None

        focus_nodes = native_target_nodes(data_graph=data, shacl_graph=shapes, shape_node=shape)

        for prop in props:
            path = next((o for _, _, o in shapes.triples((prop, SH.path, None))), None)
            if path is None:
                return None

            if any(True for _ in shapes.triples((prop, SH.or_, None))):
                return None

            component_name = _resolve_literal_only_component_name(shapes, prop)
            if component_name is None:
                return None

            source_component = _LITERAL_ONLY_COMPONENTS[component_name]

            for focus in focus_nodes:
                values = tuple(o for _, _, o in data.triples((focus, path, None)))
                if not values:
                    continue

                if any(isinstance(v, Literal) for v in values):
                    return None

                request = ComponentRequest(
                    component={"name": component_name},
                    focus_node=focus,
                    value_nodes=values,
                    options={},
                )
                result = native_evaluate_component(request)
                if result.conforms:
                    continue

                for violation in result.violations:
                    events.append(
                        {
                            "focus_node": focus,
                            "result_path": path,
                            "value": violation,
                            "source_constraint_component": source_component,
                        }
                    )

    report_context = Graph() if decode_report else Graph()
    report = native_build_report(events=tuple(events), graph_context=report_context, options=None)
    diagnostics = ExecutionDiagnostics(report_triples=len(report))
    return ValidationResult(
        conforms=len(events) == 0,
        report_graph=report,
        report_text="native literal-only preflight",
        data_graph=None,
        diagnostics=diagnostics,
    )


def _annotate_conformance_disallows(report_graph: Any, options: dict[str, Any], conforms: bool) -> bool:
    """Add ``sh:conformanceDisallows`` to the report per SHACL 1.2 Core:
    the set of severities whose presence makes ``sh:conforms`` false.
    ``sh:Violation`` is always disallowed; ``sh:Warning``/``sh:Info`` are
    disallowed unless ``options['allow_warnings']``/``['allow_infos']``
    is set, letting a caller opt into treating warning/info-level results
    as non-blocking.

    Also recomputes ``sh:conforms`` itself from the report's actual
    result severities (rewriting the triple in ``report_graph`` to
    match) rather than trusting pySHACL's own boolean as-is, since
    pySHACL's default notion of conformance only ever considers
    ``sh:Violation``.

    Args:
        report_graph: The decoded validation report graph to annotate
            in place.
        options: The resolved validation options; reads
            ``allow_warnings``/``allow_infos``.
        conforms: pySHACL's own conformance boolean, returned unchanged
            if no ``sh:ValidationReport`` node is found.

    Returns:
        The recomputed conformance boolean.
    """
    report_node = _find_genuine_report_node(report_graph)
    if report_node is None:
        return conforms

    disallowed = {SH.Violation}
    if not options.get("allow_warnings"):
        disallowed.add(SH.Warning)
    if not options.get("allow_infos"):
        disallowed.add(SH.Info)

    report_graph.remove((report_node, SH.conformanceDisallows, None))
    for severity in disallowed:
        report_graph.add((report_node, SH.conformanceDisallows, severity))

    blocking = any(
        set(report_graph.objects(result_node, SH.resultSeverity)) & disallowed
        for _, _, result_node in report_graph.triples((report_node, SH.result, None))
    )
    new_conforms = not blocking
    report_graph.remove((report_node, SH.conforms, None))
    report_graph.add((report_node, SH.conforms, Literal(new_conforms)))
    return new_conforms


def _merge_derived_conforms_to(
    report_graph: Any,
    data_graph_iri: Any | None,
    shapes_graph_iri: Any | None,
    specification_graph: Any | None = None,
) -> None:
    """Automatically derive and merge SHACL 1.2 Profiling S5.5's
    ``sh:conformsTo``/``dcterms:conformsTo`` triples into ``report_graph``,
    whenever both ``data_graph_iri=`` and ``shapes_graph_iri=`` are
    already resolved - the one case where both of
    ``derive_conforms_to()``'s own required graph identities are
    unambiguously known, so there's nothing left for a caller to supply
    via a separate call. Never guesses either identity itself.

    Called unconditionally (not gated on ``conforms``) - a non-conforming
    report simply derives nothing, matching the rule's own ``sh:conforms
    true`` requirement; ``derive_conforms_to()`` already self-limits
    correctly on its own, no extra check needed here.

    ``specification_graph``, when also given, is forwarded straight
    through to ``derive_conforms_to()`` so S5.5's *second* rule fires too
    in the same pass - ``dcterms:conformsTo`` the specification the
    shapes graph itself is a ``prof:isProfileOf``, not just
    ``sh:conformsTo`` the shapes graph.

    Relies on ``_annotate_used_graphs_and_configuration`` having already
    run first (same caller, immediately before this) - that call already
    wrote the coerced ``sh:usedDataGraph``/``sh:usedShapesGraph`` triples
    onto ``report_graph``, which ``derive_conforms_to()`` reads directly
    rather than needing ``data_graph_iri``/``shapes_graph_iri`` passed to
    it a second time.

    Deliberately does **not** attempt to keep ``report_text`` in sync - it's
    a plain string pySHACL rendered before this triple ever existed, not a
    live view of ``report_graph``; re-rendering it would mean duplicating
    pySHACL's own formatting logic for one extra triple. A known,
    documented gap, not an oversight - see ``starlayer/shacl/CLAUDE.md``'s
    dated entry.

    Only fires when **both** IRIs are present - never just one, matching
    ``derive_conforms_to()``'s own requirement that both graph identities
    be resolvable before its underlying rule can fire at all (it would
    otherwise raise ``ValueError`` for the missing one). ``specification_graph``
    alone, with no IRIs, still does nothing - the second rule has no
    triple to chain from without the first one having fired."""
    if data_graph_iri is None or shapes_graph_iri is None:
        return
    from starlayer.shacl.profiling import derive_conforms_to

    # Not conforms_only=True here - this call site needs the
    # sh:validationReport link too (not just the bare conformsTo
    # triples), so it can land on report_graph. derive_conforms_to()'s
    # default result already contains report_graph's own triples plus
    # everything newly derived (link included) - merging it back in is
    # a safe no-op for what report_graph already had and a real add for
    # what's new, since RDF graphs are sets.
    merged = derive_conforms_to(report_graph, specification_graph=specification_graph)
    report_graph += merged


def _rebuild_report_namespaces(
    report_graph: Any,
    *,
    specification_graph: Any | None,
    data_graph: Any | None,
    shacl_graph: Any | None,
    ont_graph: Any | None,
) -> None:
    """Replace ``report_graph``'s wholesale-inherited namespace bindings
    with a clean, deliberate set.

    ``adapters.py``'s ``decode_graph()`` adopts pySHACL's own internal
    ``Graph()``'s ``namespace_manager`` directly (``decoded.namespace_manager
    = getattr(graph, "namespace_manager", None)``) - and a bare
    ``rdflib.Graph()`` with no explicit ``bind_namespaces=`` picks up
    rdflib's own ~29-entry default vocabulary table (``brick``/``csvw``/
    ``dcat``/.../``ex``/...), none of which starlayer.shacl ever asked
    for. ``ex`` resolving to ``http://example.org/`` in particular is
    pure accident of that table, not anything this project deliberately
    chose.

    Rebuilt from a fresh ``bind_namespaces="core"`` base (``rdf``/``rdfs``/
    ``owl``/``xsd``/``xml`` only - note ``sh`` is *not* in rdflib's own
    "core" set either, despite every report using it constantly) plus an
    explicit ``sh`` binding, then each real input graph's own bound
    prefixes are layered on top, in priority order: ``specification_graph``
    (the caller's most deliberately-chosen vocabulary - e.g. a business-
    policy namespace - and the one most worth preserving as-is), then
    ``data_graph``, then ``shacl_graph``, then ``ont_graph``. First-bound-
    wins throughout (including against the ``core``+``sh`` base) - a
    later source can never silently override an earlier one's choice of
    label for the same prefix string.
    """
    nm = NamespaceManager(report_graph, bind_namespaces="core")
    nm.bind("sh", SH)
    report_graph.namespace_manager = nm

    for source in (specification_graph, data_graph, shacl_graph, ont_graph):
        if source is None:
            continue
        source_nm = getattr(source, "namespace_manager", None)
        if source_nm is None:
            continue
        for prefix, namespace in source_nm.namespaces():
            if nm.store.namespace(prefix) is None:
                nm.bind(prefix, namespace)


def _relabel_validation_report_node(report_graph: Any) -> None:
    """Give the ``sh:ValidationReport`` node a short, stable local label
    (``_:report``) instead of pySHACL's own randomly-generated long hex
    ``BNode`` - purely for readability now that ``sh:validationReport``
    (and the ``Provenance:`` appendix below) both print/serialize a
    direct reference to it.

    Still an ordinary blank node - RDF gives blank node labels no
    identity outside the one graph/serialization they appear in, so this
    carries no guarantee across a parse/merge/reserialize round trip, same
    as any other blank node. A caller who merges more than one separately-
    produced ``report_graph`` under this same fixed label would collide -
    exactly the hazard pySHACL's own randomized label exists to avoid;
    ``Graph.skolemize()``/``.de_skolemize()`` first if that's ever a real
    need. A single report consumed on its own - the normal case here - is
    unaffected.

    Args:
        report_graph: The decoded validation report graph, relabeled in
            place. No-op if no ``sh:ValidationReport`` node is found, or
            if it's already a ``URIRef`` rather than a ``BNode``.

    Returns:
        None - mutates ``report_graph`` in place.
    """
    report_node = _find_genuine_report_node(report_graph)
    if report_node is None or not isinstance(report_node, BNode):
        return
    new_node = BNode("report")
    if new_node == report_node:
        return
    for s, p, o in list(report_graph.triples((report_node, None, None))):
        report_graph.remove((s, p, o))
        report_graph.add((new_node, p, o))
    for s, p, o in list(report_graph.triples((None, None, report_node))):
        report_graph.remove((s, p, o))
        report_graph.add((s, p, new_node))


def _append_provenance_to_report_text(report_text: str, report_graph: Any, data_graph_iri: Any | None) -> str:
    """Append a small, deterministic provenance appendix to pySHACL's own
    ``report_text`` - the one thing it never reflects, since pySHACL
    renders that string before ``_annotate_used_graphs_and_configuration``/
    ``_merge_derived_conforms_to`` ever run, so none of
    ``sh:usedDataGraph``/``sh:usedShapesGraph``/``sh:conformsTo``/
    ``dcterms:conformsTo`` exist yet at that point (see this file's own
    "report_text is not kept in sync" note).

    Deliberately additive only - never touches or re-derives pySHACL's own
    violation listing, which would mean duplicating its own formatting
    logic for every severity/focus-node/path case it already handles.
    Deliberately does not surface ``sh:validationReport`` itself here (a
    blank node label has no meaning worth printing in plain text) and does
    not turn ``report_text`` into an RDF property of the report node
    either - both considered and rejected as unneeded complexity for what
    this appendix is for.

    Every value renders via the report graph's own bound prefixes
    (``term.n3(report_graph.namespace_manager)``), matching how
    ``report_graph.serialize()`` already reads - falls back to the full
    ``<...>`` form for anything unbound, same as any other n3 rendering.
    A line appears only when there is something to say. ``Used Data
    Graph``/``Used Shapes Graph`` are listed only when the report has the
    corresponding ``sh:usedDataGraph``/``sh:usedShapesGraph``, and
    ``sh:conformsTo``/``dcterms:conformsTo`` render as one real
    subject-predicate-object sentence per triple found (e.g.
    ``ex:data1 sh:conformsTo ex:AliceShapesGraph .``) - never as a "Not
    specified" placeholder. When nothing at all is known (no data graph
    or shapes graph identity was given or resolved), no ``Provenance:``
    block is added and ``report_text`` is returned unchanged: the report
    makes no statement it has no data for, the same way ``report_graph``
    omits those triples.

    Args:
        report_text: pySHACL's own rendered report string to append to.
        report_graph: The decoded report graph to read provenance
            triples from (``sh:usedDataGraph``/``sh:usedShapesGraph``/
            ``sh:conformsTo``/``dcterms:conformsTo``).
        data_graph_iri: The data graph's resolved identity, used to look
            up ``sh:conformsTo``/``dcterms:conformsTo`` triples on it;
            if ``None``, no ``conformsTo`` line is added.

    Returns:
        ``report_text`` unchanged if no ``sh:ValidationReport`` node is
        found in ``report_graph`` or there is no provenance to report,
        otherwise ``report_text`` with the provenance appendix appended.
    """
    report_node = _find_genuine_report_node(report_graph)
    if report_node is None:
        return report_text

    nm = report_graph.namespace_manager

    def _n3(term: Any) -> str:
        return term.n3(nm)


    data_graph_subject = None
    if data_graph_iri is not None:
        data_graph_subject = (
            data_graph_iri if isinstance(data_graph_iri, (URIRef, Literal)) else URIRef(str(data_graph_iri))
        )

    conforms_to_triples: list = []
    if data_graph_subject is not None:
        for predicate in (SH.conformsTo, DCTERMS.conformsTo):
            for obj in report_graph.objects(data_graph_subject, predicate):
                conforms_to_triples.append((data_graph_subject, predicate, obj))

    lines: list[str] = []
    for label, predicate in (("Used Data Graph", SH.usedDataGraph), ("Used Shapes Graph", SH.usedShapesGraph)):
        values = list(report_graph.objects(report_node, predicate))
        if values:
            lines.append(f"\t{label}: {', '.join(_n3(v) for v in values)}")
    lines.extend(f"\t{_n3(s)} {_n3(p)} {_n3(o)} ." for s, p, o in conforms_to_triples)

    if not lines:
        return report_text
    return report_text + "\n".join(["", "Provenance:", *lines])


def _annotate_used_graphs_and_configuration(
    report_graph: Any,
    *,
    data_graph_iri: Any | None,
    shapes_graph_iri: Any | None,
    include_used_configuration: bool,
) -> None:
    """Add ``sh:usedDataGraph``/``sh:usedShapesGraph``/``sh:usedConfiguration``
    to the report's ``sh:ValidationReport`` node, per SHACL 1.2 Core
    section 6.7.1.5-6.7.1.8 - no-op if that node isn't found.

    ``sh:usedDataGraph``/``sh:usedShapesGraph`` are added only when their
    respective IRI argument is not ``None``, coerced to a ``URIRef``
    unless already a ``URIRef``/``Literal`` (SHACL 1.2 Core allows a
    versioned graph identity to be given as a literal). When
    ``include_used_configuration`` is true, a fresh blank node typed
    ``sh:ProcessorConfiguration`` is created and linked via
    ``sh:usedConfiguration`` - this project never records any real
    configuration options on it, just the bare required triple.

    Args:
        report_graph: The decoded validation report graph to annotate
            in place.
        data_graph_iri: The data graph's resolved identity, or ``None``
            to omit ``sh:usedDataGraph``.
        shapes_graph_iri: The shapes graph's resolved identity, or
            ``None`` to omit ``sh:usedShapesGraph``.
        include_used_configuration: Whether to add the bare
            ``sh:usedConfiguration`` triple.

    Returns:
        None - mutates ``report_graph`` in place.
    """
    report_node = _find_genuine_report_node(report_graph)
    if report_node is None:
        return

    if data_graph_iri is not None:
        value = data_graph_iri if isinstance(data_graph_iri, (URIRef, Literal)) else URIRef(str(data_graph_iri))
        report_graph.add((report_node, SH.usedDataGraph, value))
    if shapes_graph_iri is not None:
        value = (
            shapes_graph_iri
            if isinstance(shapes_graph_iri, (URIRef, Literal))
            else URIRef(str(shapes_graph_iri))
        )
        report_graph.add((report_node, SH.usedShapesGraph, value))
    if include_used_configuration:
        config_node = BNode()
        report_graph.add((config_node, RDF.type, SH.ProcessorConfiguration))
        report_graph.add((report_node, SH.usedConfiguration, config_node))


def _humanize_report_text(report_text: str, adapter: TripleTermAdapter) -> str:
    """Replace encoded triple-term URIs embedded in pySHACL's report text
    with a readable ``<<( s p o )>>`` rendering - string substitution
    against ``adapter``'s own encoding registry, applied repeatedly so
    nested triple terms resolve fully (a triple term nested inside
    another only becomes substitutable once its own containing term has
    already been rewritten).

    Args:
        report_text: pySHACL's own rendered report string, containing
            zero or more encoded ``tt:HASH`` URIs in angle brackets.
        adapter: The ``TripleTermAdapter`` whose registry maps each
            encoded URI back to its ``(s, p, o)`` components.

    Returns:
        ``report_text`` unchanged if the adapter's registry is empty,
        otherwise with every encoded triple-term URI replaced.
    """
    registry = adapter.export_registry()
    entries = registry.get("entries", [])
    if not entries:
        return report_text

    substitutions = {
        f"<{entry['uri']}>": f"<<( {entry['s']} {entry['p']} {entry['o']} )>>" for entry in entries
    }

    for _ in range(len(substitutions) + 1):
        changed = False
        for encoded, readable in substitutions.items():
            if encoded in report_text:
                report_text = report_text.replace(encoded, readable)
                changed = True
        if not changed:
            break

    return report_text


def _try_native_core_validation(
    *,
    data_graph: Any,
    shacl_graph: Any | None,
    decode_report: bool,
) -> ValidationResult | None:
    """Try the native literal-only fast path first, then the native
    structural-property fast path, returning whichever succeeds.

    Args:
        data_graph: The data graph to validate.
        shacl_graph: The shapes graph to validate against, or ``None``
            (both fast paths then return ``None`` immediately).
        decode_report: Forwarded to each fast path, controlling whether
            its (currently unused either way) report-decoding context is
            built.

    Returns:
        The first non-``None`` ``ValidationResult`` from either fast
        path, or ``None`` if neither applies - meaning the caller should
        fall back to full pySHACL validation.
    """
    literal_only = _try_native_literal_only_validation(
        data_graph=data_graph,
        shacl_graph=shacl_graph,
        decode_report=decode_report,
    )
    if literal_only is not None:
        return literal_only

    structural = _try_native_structural_property_validation(
        data_graph=data_graph,
        shacl_graph=shacl_graph,
        decode_report=decode_report,
    )
    if structural is not None:
        return structural

    return None


def _resolve_literal_only_component_name(shapes: Any, prop: Any) -> str | None:
    """Return the single literal-only SHACL component name (from
    ``_LITERAL_ONLY_COMPONENTS`` - ``pattern``/``datatype``/
    ``languageIn``/``minLength``/``maxLength``) declared on property
    shape ``prop``, or ``None`` if zero or more than one of them is
    present.

    Args:
        shapes: The shapes graph ``prop`` is defined in.
        prop: The property shape to inspect.

    Returns:
        The one present component's name, or ``None``.
    """
    present: list[str] = []
    for name in _LITERAL_ONLY_COMPONENTS:
        predicate = SH[name]
        if any(True for _ in shapes.triples((prop, predicate, None))):
            present.append(name)

    if len(present) != 1:
        return None
    return present[0]


def _try_native_structural_property_validation(
    *,
    data_graph: Any,
    shacl_graph: Any | None,
    decode_report: bool,
) -> ValidationResult | None:
    """Attempt a fast, native-only validation path for the structural
    counterpart of ``_try_native_literal_only_validation``: node shapes
    whose property shapes each declare exactly one structural component
    (``sh:hasValue``/``sh:in``/``sh:equals``/``sh:disjoint`` - see
    ``_resolve_structural_component_definition``), where ``equals``/
    ``disjoint`` compare against another property path's own values
    rather than requiring literal-only values.

    Returns ``None`` (meaning: fall back to full pySHACL validation)
    whenever ``shacl_graph`` is ``None``, there are no node shapes, any
    node shape has ``sh:rule``/no ``sh:property``, or any property shape
    has no ``sh:path``/doesn't resolve to exactly one well-formed
    structural component definition. Otherwise evaluates every component
    via ``native_evaluate_component`` (threading in the other path's
    values for ``equals``/``disjoint``) and returns a ``ValidationResult``
    built from the resulting violation events.
    """
    if shacl_graph is None:
        return None

    data = normalize_graph_inputs(data_graph, None, None)[0]
    shapes = normalize_graph_inputs(shacl_graph, None, None)[0]

    node_shapes = tuple(s for s, _, _ in shapes.triples((None, RDF.type, SH.NodeShape)))
    if not node_shapes:
        return None

    events: list[dict[str, Any]] = []

    for shape in node_shapes:
        if any(True for _ in shapes.triples((shape, SH.rule, None))):
            return None

        props = tuple(o for _, _, o in shapes.triples((shape, SH.property, None)))
        if not props:
            return None

        focus_nodes = native_target_nodes(data_graph=data, shacl_graph=shapes, shape_node=shape)

        for prop in props:
            path = next((o for _, _, o in shapes.triples((prop, SH.path, None))), None)
            if path is None:
                return None

            structural = _resolve_structural_component_definition(shapes, prop)
            if structural is None:
                return None

            component_name, component_args = structural
            source_component = _STRUCTURAL_COMPONENTS[component_name]

            for focus in focus_nodes:
                values = tuple(o for _, _, o in data.triples((focus, path, None)))
                if not values:
                    continue

                component = {"name": component_name}
                component.update(component_args)
                if component_name in {"equals", "disjoint"}:
                    other_path = component_args["other_path"]
                    component = {
                        "name": component_name,
                        "other_values": tuple(o for _, _, o in data.triples((focus, other_path, None))),
                    }

                request = ComponentRequest(
                    component=component,
                    focus_node=focus,
                    value_nodes=values,
                    options={},
                )
                result = native_evaluate_component(request)
                if result.conforms:
                    continue

                for violation in result.violations:
                    events.append(
                        {
                            "focus_node": focus,
                            "result_path": path,
                            "value": violation,
                            "source_constraint_component": source_component,
                        }
                    )

    report_context = Graph() if decode_report else Graph()
    report = native_build_report(events=tuple(events), graph_context=report_context, options=None)
    diagnostics = ExecutionDiagnostics(report_triples=len(report))
    return ValidationResult(
        conforms=len(events) == 0,
        report_graph=report,
        report_text="native structural-property preflight",
        data_graph=None,
        diagnostics=diagnostics,
    )


def _resolve_structural_component_definition(shapes: Any, prop: Any) -> tuple[str, dict[str, Any]] | None:
    """Resolve property shape ``prop``'s single structural SHACL
    component - ``sh:hasValue``, ``sh:in``, ``sh:equals``, or
    ``sh:disjoint`` - into a ``(component_name, component_args)`` pair
    ready for ``native_evaluate_component``, or ``None`` if zero or more
    than one of the four is declared, or if the one declared value isn't
    itself well-formed for that component.

    ``hasValue``/``equals``/``disjoint`` each require exactly one object
    value; ``in`` requires exactly one ``rdf:List``-valued object,
    expanded into a tuple of allowed values via ``Collection`` (``None``
    if it doesn't parse as a well-formed list). ``equals``/``disjoint``
    return ``other_path`` (the path whose own values the caller compares
    against) rather than a literal value.

    Args:
        shapes: The shapes graph ``prop`` is defined in.
        prop: The property shape to inspect.

    Returns:
        ``(component_name, component_args)``, or ``None`` if ``prop``
        doesn't declare exactly one well-formed structural component.
    """
    has_values = tuple(o for _, _, o in shapes.triples((prop, SH.hasValue, None)))
    in_values = tuple(o for _, _, o in shapes.triples((prop, SH["in"], None)))
    equals_values = tuple(o for _, _, o in shapes.triples((prop, SH.equals, None)))
    disjoint_values = tuple(o for _, _, o in shapes.triples((prop, SH.disjoint, None)))

    present = sum(bool(v) for v in (has_values, in_values, equals_values, disjoint_values))
    if present != 1:
        return None

    if has_values:
        if len(has_values) != 1:
            return None
        return "hasValue", {"value": has_values[0]}

    if in_values:
        if len(in_values) != 1:
            return None
        try:
            allowed = tuple(Collection(shapes, in_values[0]))
        except Exception:
            return None
        return "in", {"allowed": allowed}

    if equals_values:
        if len(equals_values) != 1:
            return None
        return "equals", {"other_path": equals_values[0]}

    if len(disjoint_values) != 1:
        return None
    return "disjoint", {"other_path": disjoint_values[0]}


def validate(
    data_graph: Any,
    shacl_graph: Any | None = None,
    ont_graph: Any | None = None,
    *,
    adapter: TripleTermAdapter | None = None,
    validate_fn: Callable[..., tuple[bool, Graph, str]] | None = None,
    mode: str | ValidationMode | None = None,
    decode_report: bool = True,
    rdfs_subclass_reasoning_includes_shapes_graph: bool = False,
    shapes_graph_loader: Callable[[Any], Any | None] | None = None,
    ignore_imports: bool = False,
    meta_shapes_extra: Iterable[Any] = (),
    data_graph_iri: Any | None = None,
    shapes_graph_iri: Any | None = None,
    specification_graph: Any | None = None,
    include_used_configuration: bool = False,
    **kwargs: Any,
) -> ValidationResult:
    """Validates ``data_graph`` against ``shacl_graph`` per SHACL 1.2
    Core, and returns a ``ValidationResult``.

    Applies every SHACL 1.2 pattern this project supports natively first
    - entailment, new target types, node expressions, native component
    registration, and so on. ``StarShaclSchema.validate()`` keeps its
    own, separate copy of this body for now rather than delegating here
    - see this module's "two-step flip" note.

    Args:
        data_graph: The RDF data to validate. Normalized via
            ``normalize_graph_inputs`` (any rdflib-compatible graph
            becomes a ``StarLayerGraph``).
        shacl_graph: The shapes graph. ``None`` lets pySHACL look for
            shapes embedded directly in ``data_graph`` itself
            (pySHACL's own "data graph doubles as shapes graph"
            allowance).
        ont_graph: An optional ontology graph. Its own axioms (e.g.
            ``rdfs:domain``/``range``) are visible to entailment and to
            pySHACL's own validation run, but its triples are never
            copied into ``data_graph``, and it is never mutated.
        adapter: The ``TripleTermAdapter`` used to encode RDF-1.2
            triple terms into the plain RDF-1.1 form pySHACL
            understands, and decode its report/data back afterward.
            Defaults to a fresh ``TripleTermAdapter()``.
        validate_fn: The callable actually invoked to perform
            validation, taking ``data_graph=``/``shacl_graph=``/
            ``ont_graph=`` (already encoded) plus every resolved
            option as keyword arguments, and returning ``(conforms,
            report_graph, report_text)``. Defaults to
            ``_default_validate`` (a thin wrapper around
            ``pyshacl.validate``).
        mode: Selects a named preset bundle of pySHACL options (e.g.
            ``"validation"``/``"rules"``/``"debug"``) via
            ``resolve_mode_options()``; any of its options can be
            overridden per call via ``**kwargs``.
        decode_report: Whether to decode ``report_graph``'s
            triple-term encoding back into real RDF-1.2 triple terms,
            and humanize ``report_text`` to match, before returning.
            ``False`` returns both in their raw, pySHACL-native encoded
            form.
        rdfs_subclass_reasoning_includes_shapes_graph: When ``True``,
            ``sh:rootClass``'s ``rdfs:subClassOf`` lookups also consult
            ``shacl_graph``'s own subclass triples (injected into a
            copy of ``data_graph`` for the duration of the call), not
            just ``data_graph``'s.
        shapes_graph_loader: A loader resolving ``shacl_graph``'s
            declared ``owl:imports`` (via
            ``StarLayerGraph.resolve_imports()``). When given, imports
            are resolved before validation; when omitted, any import
            that isn't already locally satisfied raises ``ValueError``
            unless ``ignore_imports=True``.
        ignore_imports: Suppresses the "unresolved ``owl:imports``"
            error above when no ``shapes_graph_loader`` is given - for
            a ``shacl_graph`` whose imports were already resolved by
            the caller beforehand (or are deliberately being left
            unresolved).
        meta_shapes_extra: Extra graphs passed through to
            ``starlayer.shacl.meta_shapes.meta_validate()`` when the
            resolved options enable ``meta_shacl``.
        data_graph_iri: Recorded on the report as ``sh:usedDataGraph``.
            Falls back to ``data_graph.identifier`` when that's a real
            ``URIRef`` (not an anonymous ``BNode``) and no explicit
            value was given.
        shapes_graph_iri: Recorded on the report as
            ``sh:usedShapesGraph``, with the same ``.identifier``
            fallback as ``data_graph_iri``.
        specification_graph: Passed to
            ``starlayer.shacl.profiling.derive_conforms_to()`` so SHACL
            1.2 Profiling's second rule can additionally derive a
            ``dcterms:conformsTo`` triple from an already-derived
            ``sh:conformsTo`` one - a no-op unless both
            ``data_graph_iri`` and ``shapes_graph_iri`` resolve to
            something.
        include_used_configuration: Whether
            ``_annotate_used_graphs_and_configuration()`` also records
            which validation options were in effect, alongside
            ``sh:usedDataGraph``/``sh:usedShapesGraph``.
        **kwargs: Per-call overrides merged into ``mode``'s preset
            options (e.g. ``advanced``, ``inplace``, ``meta_shacl``,
            ``allow_warnings``, ``allow_infos``, ``inference``,
            ``debug``), forwarded to ``validate_fn``.

    Returns:
        A ``ValidationResult``: ``conforms`` (bool), ``report_graph``/
        ``report_text`` (the validation report, decoded unless
        ``decode_report=False``), ``data_graph`` (the mutated original
        when the resolved options include ``inplace=True``, otherwise
        ``None``), and ``diagnostics`` (an ``ExecutionDiagnostics``
        snapshot of adapter encode/decode activity for this call).
    """
    adapter = adapter or TripleTermAdapter()
    validate_fn = validate_fn or _default_validate
    adapter.reset_diagnostics()

    register_native_components()
    _patch_rdflib_data_graph_clone_preserves_tt_adapter()
    _patch_shape_value_nodes_for_sh_values()
    _patch_rules_apply_for_layer_and_run_once()
    _patch_stringify_for_native_backend_bnodes()

    options = resolve_mode_options(mode, overrides=kwargs)

    data_graph, shacl_graph, ont_graph = normalize_graph_inputs(
        data_graph,
        shacl_graph,
        ont_graph,
    )

    # data_graph_iri=/shapes_graph_iri= also fall back to the graph's own
    # .identifier (2026-10-09), when it's a real URIRef the caller
    # explicitly gave it at construction - never the default random BNode
    # every rdflib Graph otherwise gets, which carries no meaningful
    # identity to report. An explicit data_graph_iri=/shapes_graph_iri= is
    # never overridden. Mirrors the identical fallback on
    # StarShaclSchema.validate()'s own body - see that method's docstring/
    # CLAUDE.md for the full design.
    if data_graph_iri is None and isinstance(data_graph.identifier, URIRef):
        data_graph_iri = data_graph.identifier
    if shapes_graph_iri is None and shacl_graph is not None and isinstance(shacl_graph.identifier, URIRef):
        shapes_graph_iri = shacl_graph.identifier

    ensure_graph_mutable(data_graph, name="data_graph")

    # SHACL 1.2 Core §1.4: a shapes graph's own sh:entailment
    # declaration(s) MUST be provided before/during validation - applied
    # here, once, up front, so every downstream step sees the same
    # entailed data graph uniformly. A no-op when shacl_graph declares no
    # sh:entailment and inference= isn't given either (the common case).
    # inplace= is threaded through from the resolved mode options, not
    # hardcoded - see apply_entailment()'s own docstring for the real
    # regression this fixed. Reassign data_graph itself: when
    # inplace=False this returns a *new* graph, not the original.
    # ont_graph is threaded through too (2026-10-07) - entailment is
    # *computed* over data_graph union ont_graph (so an axiom declared
    # only in ont_graph, the idiomatic place for rdfs:domain/range/etc.,
    # is actually seen), but only the newly-entailed delta is
    # materialized - ont_graph's own raw triples are never copied in, and
    # ont_graph itself is never mutated.
    #
    # inference= (2026-10-08) is popped out of options here so it's never
    # also forwarded to pySHACL's own validate_fn below - and now shares
    # sh:entailment's own real ENTAILMENT.* IRI vocabulary directly
    # (apply_entailment()'s own inference= parameter just merges it into
    # whatever shacl_graph declares before materializing), rather than
    # pySHACL's own ad-hoc string vocabulary ("rdfs"/"owlrl"/"both"/etc.) -
    # see starlayer.shacl.entailment's own module docstring for the full
    # account of why that string-compat layer was removed, not just
    # changed.
    inference_option = options.pop("inference", None)
    from starlayer.shacl.entailment import apply_entailment

    data_graph = apply_entailment(
        data_graph, shacl_graph, ont_graph, inplace=options.get("inplace", False), inference=inference_option
    )

    # sh:filterShape (SHACL-AF node expressions) is a confirmed pySHACL
    # bug - see _patch_shape_validate_for_filter_shape's own docstring.
    if shacl_graph is not None and any(True for _ in shacl_graph.triples((None, SH.filterShape, None))):
        if not _patch_shape_validate_for_filter_shape():
            raise NotImplementedError(
                "sh:filterShape is not supported: pySHACL's own implementation crashes "
                "(AttributeError: 'RdfLibDataGraph' object has no attribute 'sparql_mode') "
                "whenever it's actually used, confirmed with plain RDF 1.1 data, and "
                "starShacl's compatibility workaround could not be applied against this "
                "pySHACL version - see docs/upstream-issues/pyshacl-upstream-issues.md."
            )

    # SHACL 1.2 Node Expressions moved to the shnex: namespace - pySHACL
    # 0.40.0 only knows the old sh:union/sh:intersection/sh:filterShape/
    # sh:path forms. A shapes graph using ONLY sparql: node expressions
    # (no shnex: at all) is legitimate too, hence checking both.
    if shacl_graph is not None and any(
        True
        for p in shacl_graph.predicates()
        if str(p).startswith(str(SHNEX)) or str(p).startswith(str(SPARQL_EXPR_NS))
    ):
        from starlayer.shacl.node_expressions import patch_node_expressions_for_shnex

        if not patch_node_expressions_for_shnex():
            raise NotImplementedError(
                "shnex:/sparql: (SHACL 1.2 Node Expressions) predicates were found in "
                "the shapes graph, but starShacl's support could not be wired into "
                "this pySHACL version - see starlayer.shacl/node_expressions.py."
            )

    # sh:expression's own scope-seeding bug affects *any* sh:expression
    # usage, not just shnex:/sparql:-tagged ones - gated separately from
    # the shnex:/sparql: check above for exactly that reason.
    if shacl_graph is not None and any(True for _ in shacl_graph.triples((None, SH.expression, None))):
        if not _patch_expression_constraint_for_value_scope():
            raise NotImplementedError(
                "sh:expression is not supported: pySHACL's own implementation passes the "
                "wrong node as focusNode and never binds \"value\" in scope (see the SHACL "
                "1.2 Node Expressions spec's sh:expression TEXTUAL DEFINITION), and "
                "starShacl's fix could not be applied against this pySHACL version."
            )

    # SHACL 1.2 Core: a shapes graph can cross-reference reusable modules
    # via owl:imports. Retrieval is delegated to a caller-supplied
    # shapes_graph_loader.
    #
    # ignore_imports (2026-10-08): see StarShaclSchema.validate()'s own
    # identical block for the full reasoning - raises by default when
    # shacl_graph declares owl:imports that aren't already locally
    # satisfied (has_import_locally()) and no loader was given, since a
    # shape referencing something only defined in a genuinely unresolved
    # import would otherwise simply never fire with no indication
    # anything was skipped. Pass ignore_imports=True if the imports were
    # already resolved into shacl_graph yourself beforehand (the
    # owl:imports triple itself isn't removed by resolve_imports() once
    # resolved via a loader, so its presence can't by itself distinguish
    # "already handled via a loader" from "genuinely missing" -
    # has_import_locally() only catches the already-co-located case).
    if shacl_graph is not None and shapes_graph_loader is not None:
        shacl_graph = _resolve_shapes_graph_imports(shacl_graph, graph_loader=shapes_graph_loader)
    elif shacl_graph is not None and not ignore_imports:
        declared_imports = [o for o in shacl_graph.owl_imports() if not shacl_graph.has_import_locally(o)]
        if declared_imports:
            raise ValueError(
                f"shacl_graph declares owl:imports {declared_imports!r} that aren't already "
                "locally satisfied, but no shapes_graph_loader was given to resolve them. "
                "Pass shapes_graph_loader=... to resolve them, or ignore_imports=True if "
                "you've already resolved them yourself (or don't need them)."
            )

    # SHACL 1.2's new target types are unknown to pySHACL - pre-compute
    # the extra target nodes and inject them as ordinary sh:targetNode
    # triples, which pySHACL already fully supports.
    shacl_graph = _augment_shapes_with_new_target_types(data_graph, shacl_graph)

    # sh:deactivated [ shnex:.../sparql:... ]: see
    # _strip_deactivated_node_expressions's own docstring.
    shacl_graph, deactivated_expr_registry = _strip_deactivated_node_expressions(shacl_graph)

    # Predicates registered as real pySHACL constraint components whose
    # value is itself a referenced shape need that value explicitly
    # typed, or pySHACL's own shape-graph loader won't recognize it.
    shacl_graph = _ensure_native_component_shapes_typed(shacl_graph)

    # pySHACL's own meta_shacl=True mechanism has no SHACL 1.2 awareness -
    # starlayer.shacl.meta_shapes fully replaces it (not supplements it).
    if shacl_graph is not None and options.get("meta_shacl"):
        from starlayer.shacl.meta_shapes import meta_validate

        meta_validate(
            shacl_graph,
            inference=options.get("inference"),
            extra_graphs=meta_shapes_extra,
            allow_warnings=options.get("allow_warnings"),
            allow_infos=options.get("allow_infos"),
        )
        from starlayer.shacl.meta_shapes import check_sparql_query_text

        check_sparql_query_text(shacl_graph)
    options.pop("meta_shacl", None)

    # Every SHACL 1.2 predicate pySHACL doesn't natively implement is now
    # registered as a real pySHACL constraint component or handled by one
    # of the other patterns in docs/shacl12-gap-matrix.md's "Note on
    # Architecture Direction".
    if _graph_contains_triple_terms(data_graph) or _graph_contains_triple_terms(
        shacl_graph
    ) or _graph_contains_triple_terms(ont_graph):
        native_result = _try_native_core_validation(
            data_graph=data_graph,
            shacl_graph=shacl_graph,
            decode_report=decode_report,
        )
        if native_result is not None:
            return native_result

    shapes_for_pyshacl = shacl_graph

    # sh:rootClass needs to consult the shapes graph's own rdfs:subClassOf
    # triples too when the caller opts into that - injected into the copy
    # of data_graph handed to pySHACL, so the component can query
    # target_graph alone.
    data_for_pyshacl, injected_subclass_triples = _inject_shapes_graph_subclass_triples(
        data_graph,
        shacl_graph,
        enabled=rdfs_subclass_reasoning_includes_shapes_graph,
    )

    encoded_data = adapter.encode_graph(data_for_pyshacl)
    encoded_shapes = adapter.encode_graph(shapes_for_pyshacl) if shapes_for_pyshacl is not None else None
    encoded_ont = adapter.encode_graph(ont_graph) if ont_graph is not None else None

    deactivated_token = None
    if deactivated_expr_registry:
        if not _patch_shape_focus_nodes_for_deactivated_expression():
            raise NotImplementedError(
                "sh:deactivated with a node-expression value is not supported: "
                "starShacl's fix could not be applied against this pySHACL version - "
                "see starlayer.shacl/validator.py::_patch_shape_focus_nodes_for_deactivated_expression."
            )
        deactivated_token = _deactivated_expr_registry.set(deactivated_expr_registry)
    try:
        conforms, report_graph, report_text = validate_fn(
            data_graph=encoded_data,
            shacl_graph=encoded_shapes,
            ont_graph=encoded_ont,
            **options,
        )
    finally:
        if deactivated_token is not None:
            _deactivated_expr_registry.reset(deactivated_token)

    # Confirmed pySHACL bug: a pyshacl.errors.ValidationFailure raised deep
    # inside constraint evaluation is caught by pySHACL's own top-level
    # validate() and returned *as* report_graph, violating its own
    # documented (bool, Graph, str) return contract. Re-raise it directly.
    if isinstance(report_graph, BaseException):
        raise report_graph

    for triple in injected_subclass_triples:
        encoded_data.remove(triple)

    out_report = adapter.decode_graph(report_graph) if decode_report else report_graph
    if decode_report:
        report_text = _humanize_report_text(report_text, adapter)
    _rebuild_report_namespaces(
        out_report,
        specification_graph=specification_graph,
        data_graph=data_graph,
        shacl_graph=shacl_graph,
        ont_graph=ont_graph,
    )
    _relabel_validation_report_node(out_report)

    conforms = _annotate_conformance_disallows(out_report, options, conforms)
    _annotate_used_graphs_and_configuration(
        out_report,
        data_graph_iri=data_graph_iri,
        shapes_graph_iri=shapes_graph_iri,
        include_used_configuration=include_used_configuration,
    )
    _merge_derived_conforms_to(out_report, data_graph_iri, shapes_graph_iri, specification_graph)
    report_text = _append_provenance_to_report_text(report_text, out_report, data_graph_iri)

    out_data: TripleTermGraph | Any | None = None
    if options.get("inplace"):
        if _is_starlayer_graph(data_graph):
            out_data = adapter.decode_graph(encoded_data)
            adapter.replace_graph(data_graph, out_data)
            out_data = data_graph
        else:
            adapter.replace_graph(data_graph, encoded_data)
            out_data = data_graph

    snapshot = adapter.diagnostics_snapshot()
    diagnostics = ExecutionDiagnostics(
        encode_graph_calls=snapshot["encode_graph_calls"],
        decode_graph_calls=snapshot["decode_graph_calls"],
        encoded_triple_terms=snapshot["encoded_triple_terms"],
        decoded_triple_terms=snapshot["decoded_triple_terms"],
        generated_support_triples=adapter.support_triple_count(),
        encoded_data_triples=len(encoded_data),
        report_triples=len(report_graph),
        inplace_data_triples=len(out_data) if out_data is not None else 0,
    )

    return ValidationResult(
        conforms=conforms,
        report_graph=out_report,
        report_text=report_text,
        data_graph=out_data,
        diagnostics=diagnostics,
    )


def validate_each(
    data_graphs: Iterable[Any],
    shacl_graph: Any | None = None,
    ont_graph: Any | None = None,
    **kwargs: Any,
) -> dict[int, ValidationResult]:
    """Validate each graph in ``data_graphs`` against the same
    ``shacl_graph``/``ont_graph``, by calling the module-level
    ``validate()`` function above once per item.
    ``StarShaclSchema.validate_each()`` keeps its own, separate copy of
    this body for now (see ``validate()``'s own docstring).

    Args:
        data_graphs: The data graphs to validate, one at a time.
        shacl_graph: The shapes graph shared by every call - see
            ``validate()``'s own docstring for its ``None`` fallback
            and every other behavior detail.
        ont_graph: The ontology graph shared by every call - see
            ``validate()``'s own docstring.
        **kwargs: Forwarded unchanged to every ``validate()`` call
            (e.g. ``mode``, ``inference``, ``data_graph_iri``, ...).

    Returns:
        A ``dict`` mapping each item's index in ``data_graphs`` (via
        ``enumerate``) to its own ``ValidationResult``.
    """
    return {i: validate(data_graph, shacl_graph, ont_graph, **kwargs) for i, data_graph in enumerate(data_graphs)}


def evaluate(
    data_graph: Any,
    shacl_graph: Any | None = None,
    ont_graph: Any | None = None,
    *,
    inference: Any | None = None,
) -> Any:
    """Computes every ``sh:values``/``sh:defaultValue``-declared virtual
    property across ``shacl_graph`` and returns the result as a
    shape-driven subgraph.

    A third, independent processing mode alongside ``validate()``
    (checks conformance, never mutates) and ``apply_rules()`` (executes
    ``sh:rule``, materializes real triples). ``StarShaclSchema.evaluate()``
    keeps its own, separate copy of this body for now - see
    ``validate()``'s own docstring.

    The returned graph contains every property shape's real, stored
    ``sh:path`` values for its own target focus nodes (not just the
    ones also declaring ``sh:values``/``sh:defaultValue``), plus the
    computed virtual values layered on top - never the whole of
    ``data_graph``. Only a property shape's simple, single-predicate
    ``sh:path`` is handled; a property path expression (sequence/
    inverse/etc.) is silently skipped. A computed value is unioned
    with any real, already-stored value for the same predicate, never
    replacing it (SHACL 1.2 Core's "Value Nodes of Property Shapes"
    algorithm unconditionally adds both real path-based values and
    ``sh:values``-computed values to the same set; only
    ``sh:defaultValue`` is conditional, on that set still being empty).
    The caller's own ``data_graph`` is never mutated, and the returned
    graph is not meant to be persisted - the SHACL 1.2 Node Expressions
    spec's own framing for virtual values is that they are computed
    "only on demand", never creating real triples in the data or
    shapes graph.

    Args:
        data_graph: The RDF data to evaluate virtual properties over.
        shacl_graph: The shapes graph declaring ``sh:values``/
            ``sh:defaultValue``. ``None`` falls back to ``data_graph``
            itself, matching ``validate()``'s own "data graph doubles
            as shapes graph" allowance.
        ont_graph: An optional ontology graph, visible to entailment
            the same way as in ``validate()``/``apply_rules()``.
        inference: A real ``ENTAILMENT.*`` IRI, or an iterable of
            them, merged with ``shacl_graph``'s own declared
            ``sh:entailment`` regime(s) and applied once, up front,
            onto a private, non-mutating copy of ``data_graph``. Every
            later step (target resolution, ``sh:values``/
            ``sh:defaultValue`` computation, and what counts as a
            "real, stored" value) runs against that entailed copy.
            Unlike ``apply_rules()``'s "inference graph" exclusion, an
            entailed triple here is treated exactly like an asserted
            one and can appear in the returned subgraph - a deliberate
            choice, since Core's own value-nodes algorithm itself
            never distinguishes asserted from entailed triples.

    Returns:
        A plain graph object (the same type as ``data_graph``)
        containing the shape-driven subgraph described above.
    """
    data_graph, shacl_graph, ont_graph = normalize_graph_inputs(
        data_graph, shacl_graph if shacl_graph is not None else data_graph, ont_graph
    )

    from starlayer.shacl.entailment import apply_entailment

    data_graph = apply_entailment(data_graph, shacl_graph, ont_graph, inplace=False, inference=inference)

    shacl_graph = _augment_shapes_with_new_target_types(data_graph, shacl_graph)

    from pyshacl.shapes_graph import ShapesGraph

    harvested_sg = ShapesGraph(shacl_graph)
    harvested_sg.shapes  # noqa: B018 - property getter triggers shape-cache harvest

    merged = type(data_graph)()
    for prefix, ns in data_graph.namespaces():
        merged.bind(prefix, ns)

    # Every property shape with a simple, single-predicate sh:path - not
    # just ones also declaring sh:values/sh:defaultValue - contributes its
    # real, stored triples for its own target focus nodes. The returned
    # graph is a shape-driven *subgraph* of data_graph (only the parts the
    # shapes graph actually describes via a property path), not a full
    # copy of data_graph - with virtual sh:values/sh:defaultValue output
    # layered on top of that subgraph.
    all_prop_shapes = {s for s, _, _ in shacl_graph.triples((None, SH.path, None))}

    for prop_shape in all_prop_shapes:
        path_vals = list(shacl_graph.objects(prop_shape, SH.path))
        if len(path_vals) != 1 or not isinstance(path_vals[0], URIRef):
            continue
        predicate = path_vals[0]
        values_node = next(iter(shacl_graph.objects(prop_shape, SH.values)), None)
        default_values = list(shacl_graph.objects(prop_shape, SH.defaultValue))

        focus_nodes = set(_shape_target_nodes(data_graph, shacl_graph, prop_shape))
        for node_shape, _, _ in shacl_graph.triples((None, SH.property, prop_shape)):
            focus_nodes |= _shape_target_nodes(data_graph, shacl_graph, node_shape)
        if not focus_nodes:
            continue

        real_shape = None
        if values_node is not None:
            try:
                real_shape = harvested_sg.lookup_shape_from_node(prop_shape)
            except KeyError:
                real_shape = None

        for focus_node in focus_nodes:
            stored = list(data_graph.objects(focus_node, predicate))
            for value in stored:
                merged.add((focus_node, predicate, value))

            computed = []
            if values_node is not None and real_shape is not None:
                computed = _compute_sh_values(real_shape, values_node, data_graph, focus_node)
                for value in computed:
                    merged.add((focus_node, predicate, value))
            if not stored and not computed and default_values:
                for default_value_node in default_values:
                    for value in _compute_sh_default_value(default_value_node, data_graph, harvested_sg, focus_node):
                        merged.add((focus_node, predicate, value))

    return merged


def apply_rules(
    data_graph: Any,
    shacl_graph: Any | None = None,
    ont_graph: Any | None = None,
    include_source_rule_provenance: bool = False,
    rule_set: Any | None = None,
    **kwargs: Any,
) -> RulesResult:
    """Executes SHACL rules against a private working copy of
    ``data_graph``, then validates the resulting evaluation graph.

    Covers ``sh:rule``/``sh:TripleRule``/``sh:SPARQLRule``, plus SHACL
    1.2's own ``sh:RuleSet``/``sh:sourceRule`` provenance. Mirrors
    pyshacl's own module-level ``shacl_rules()`` entry point - this is
    the real implementation; ``StarShaclSchema.apply_rules()`` delegates
    here, binding its own ``shacl_graph``/``ont_graph``.

    The caller's own ``data_graph`` object is never mutated - every
    step (rule execution, entailment, the final conformance re-check)
    runs against a fresh working copy instead. ``data_graph`` must be a
    ``StarLayerGraph`` (the working copy is built via
    ``type(data_graph)()``, and only a ``StarLayerGraph`` round-trips
    RDF-1.2 triple terms through rule execution correctly).

    Processing order: (1) the "before rules" entailment/``inference=``
    pass; (2) shape-attached rule execution, via an internal
    ``validate(..., mode="rules")`` call; (3) the separate global
    ``sh:SPARQLRule``/``sh:RuleSet`` pass; (4) entailment is re-applied,
    since global rules may have produced triples a declared regime
    should also close over; (5) a final re-validation with
    ``mode="validation"`` (not ``"rules"`` again - rules have already
    run), whose conformance result is what's actually returned.

    Args:
        data_graph: The data graph rules execute against. Must be a
            ``StarLayerGraph``; raises ``TypeError`` otherwise.
        shacl_graph: The shapes graph declaring the rules (and, when
            ``rule_set`` is given, the ``sh:RuleSet``s to select
            from). ``None`` falls back to ``data_graph`` itself, so an
            unattached global ``sh:SPARQLRule`` living directly in the
            data graph is still discovered.
        ont_graph: An optional ontology graph, visible to entailment
            the same way as in ``validate()``/``evaluate()``.
        include_source_rule_provenance: When ``True``, every triple
            produced by rule execution (shape-attached or global) gets
            a reifier recording which rule produced it, per SHACL 1.2
            SPARQL Extensions section 8.7's ``sh:sourceRule``: ``_:id
            rdf:reifies <<( s p o )>> . _:id sh:sourceRule <rule> .``
        rule_set: When given, restricts rule execution to only the
            rules belonging to the named ``sh:RuleSet``(s) (resolved
            via ``_rule_set_members()`` against the normalized shapes
            graph).
        **kwargs: Forwarded to the internal ``validate()`` calls (both
            the rule-execution pass and the final re-validation),
            after being merged into the ``"rules"``/``"validation"``
            mode presets respectively via ``resolve_mode_options()``.
            ``inference`` is read directly out of ``kwargs`` for the
            explicit before/after-rules entailment passes described
            above.

    Returns:
        A ``RulesResult`` with two fields: ``inferred_graph`` -
        strictly the triples rule execution itself produced
        (shape-attached and global rules, plus any ``sh:sourceRule``
        provenance reifiers); neither the original base triples nor
        anything any entailment regime added are included, since
        entailment is purely a computational device here, never
        persisted. ``validation`` - the full ``ValidationResult`` from
        the final re-validation pass, whose ``conforms``/
        ``report_graph``/``report_text`` reflect the complete
        evaluation graph (base ∪ rules ∪ entailment); its own
        ``data_graph`` field is always ``None`` in this context (the
        internal call uses the ``"validation"`` mode's own
        ``inplace=False`` default).
    """
    if not _is_starlayer_graph(data_graph):
        raise TypeError(
            "apply_rules() requires data_graph to be a StarLayerGraph, since rule "
            f"execution needs RDF-1.2 triple-term support - got {type(data_graph).__name__}. "
            "Convert first, e.g. StarLayerGraph.from_rdflib(data_graph)."
        )
    options = resolve_mode_options("rules", overrides=kwargs)

    # Normalized once, up front, and reused both for the validate() call
    # below and for the rule-set closure/global-rules passes - matters for
    # rule_set specifically: normalize_graph_inputs returns an
    # already-StarLayerGraph input as-is (same object, same blank node
    # identities), so reusing this one reference guarantees the rule/
    # rule-set nodes _rule_set_members() reads are the exact same nodes
    # pySHACL's own shape-attached-rule execution and
    # _global_sparql_rule_triples both see - a second, independent
    # normalize_graph_inputs call on a plain (non-StarLayerGraph) input
    # would otherwise risk producing a *different* StarLayerGraph copy
    # each time, with no guarantee blank nodes compare equal across them.
    # (When called via StarShaclSchema.apply_rules(), shacl_graph is
    # already a StarLayerGraph normalized once at construction, so this
    # is a no-op identity pass-through, not a second normalization.)
    #
    # shacl_graph=None (2026-10-08) falls back to data_graph itself as the
    # shapes source - matching pySHACL's own "data graph doubles as
    # shapes graph" allowance, already confirmed working for shape-
    # attached sh:rule execution (via validate_fn below) even before this
    # fix, since pySHACL handles that case internally. This fix extends
    # the same allowance to the global-rules pass, which previously
    # couldn't discover unattached sh:SPARQLRule nodes at all when
    # shacl_graph was omitted (normalized_shapes was None, so every
    # `if normalized_shapes is not None:` guard below silently skipped
    # global-rule discovery). normalized_shapes is read-only here (rule
    # *definitions* never change while rules execute against the
    # separate, mutable out_data copy below), so aliasing the pristine
    # original data_graph is safe even though out_data is its own copy.
    normalized_shapes = normalize_graph_inputs(shacl_graph if shacl_graph is not None else data_graph, None, None)[0]

    # data_graph itself (the caller's own object) is read here, once, and
    # never touched again - base_triples is the spec's own "base graph"
    # concept, and out_data is a private working copy that rule execution,
    # entailment, and the final conformance check all run against instead.
    base_triples: frozenset = frozenset(data_graph)
    out_data = type(data_graph)()
    for prefix, ns in data_graph.namespaces():
        out_data.bind(prefix, ns)
    for t in data_graph:
        out_data.add(t)

    # entailment_triples accumulates every triple any entailment regime
    # (sh:entailment or pySHACL's own inference=) adds to out_data across
    # this whole function, at every point it runs (before rules, and
    # twice more after - see below). Tracked explicitly via before/after
    # snapshots rather than reconstructed later, since by the end out_data
    # also contains genuine rule output that must NOT be excluded -
    # subtracting a reconstructed "whatever entailment would produce"
    # after the fact could not distinguish the two. See
    # RulesResult.inferred_graph's own docstring for why this is excluded.
    entailment_triples: set = set()

    def _apply_and_track(apply_fn) -> None:
        before = frozenset(out_data)
        apply_fn()
        entailment_triples.update(frozenset(out_data) - before)

    inference_option = kwargs.get("inference")

    # Entailment/inference= "before rules" pass, applied explicitly here -
    # not left to validate()'s own internal handling below - specifically
    # so its delta can be captured and excluded from the returned
    # inference graph. validate()'s own internal entailment/inference
    # handling (mode="rules" just below) then becomes a redundant,
    # idempotent no-op pass over an already-closed graph - the same
    # accepted pattern already used for the "after rules" re-applications
    # further down. apply_entailment() tolerates normalized_shapes=None
    # itself (2026-10-08), so this runs unconditionally - a no-op when
    # neither sh:entailment nor inference= contributes anything.
    from starlayer.shacl.entailment import apply_entailment

    _apply_and_track(
        lambda: apply_entailment(out_data, normalized_shapes, ont_graph, inplace=True, inference=inference_option)
    )

    token = None
    if include_source_rule_provenance:
        _patch_rule_apply_for_source_rule_provenance()
        token = _source_rule_buffer.set([])

    rule_set_token = None
    allowed_rule_nodes: frozenset | None = None
    if rule_set is not None:
        # normalized_shapes is never None (2026-10-08) - it falls back to
        # data_graph itself when shacl_graph is omitted, so there's always
        # a real shapes source to select rule_set's own members from.
        _patch_rule_apply_for_rule_set_filtering()
        allowed_rule_nodes = _rule_set_members(normalized_shapes, rule_set)
        rule_set_token = _rule_set_filter.set(allowed_rule_nodes)

    try:
        result = validate(
            out_data,
            normalized_shapes,
            ont_graph,
            mode="rules",
            **options,
        )

        # Encoded (s, p, o) triples captured from every patched
        # TripleRule/SPARQLRule.apply() call made during validate() above -
        # decoded below, once execution has fully finished, per SHACL 1.2
        # SPARQL Extensions section 8.7's "MUST NOT be visible to
        # executing rules" requirement.
        shape_rule_records: list[tuple[tuple[Any, Any, Any], Any]] = (
            list(_source_rule_buffer.get()) if token is not None else []
        )
    finally:
        if token is not None:
            _source_rule_buffer.reset(token)
        if rule_set_token is not None:
            _rule_set_filter.reset(rule_set_token)

    out_data = result.data_graph or out_data
    global_rule_records: list[tuple[tuple[Any, Any, Any], Any]] = []
    if normalized_shapes is not None:
        # _global_sparql_rule_triples already adds each produced triple to
        # out_data itself now (needed for its own fixpoint iteration - a
        # later round/layer must see an earlier one's output) - no
        # redundant out_data.add() here, just collect records for
        # sh:sourceRule provenance bookkeeping.
        for triple, rule_node in _global_sparql_rule_triples(
            out_data, normalized_shapes, allowed_rule_nodes=allowed_rule_nodes
        ):
            if include_source_rule_provenance:
                global_rule_records.append((triple, rule_node))

    if include_source_rule_provenance:
        # A fresh, stateless adapter is fine here - diagnostics reset every
        # call regardless, and _materialize_source_rule_provenance's own
        # docstring is explicit that it can't assume any particular adapter
        # construction (e.g. for_starlayer_graph()) was used anyway.
        adapter = TripleTermAdapter()
        _materialize_source_rule_provenance(out_data, adapter, shape_rule_records, decode=True)
        _materialize_source_rule_provenance(out_data, adapter, global_rule_records, decode=False)

    # SHACL 1.2 Core §1.4 entailment + the Inference Rules spec's own
    # "rules execute, then the evaluation graph (base ∪ every inferred
    # triple) gets validated" ordering (see starlayer/shacl/CLAUDE.md's
    # dated entry for the full design) - two real gaps this closes
    # together, not two separate changes:
    #
    # 1. The "before rules" entailment/inference= pass above can't see
    #    triples the SEPARATE global sh:SPARQLRule pass just produced
    #    (e.g. a rule asserting ex:Fido a ex:Dog, which a declared RDFS
    #    regime should also close over). Re-apply both on out_data now so
    #    the *complete* evaluation graph gets them, not just the
    #    pre-global-rules state. inplace=True unconditionally - this is
    #    the private working copy, not the caller's object; the common
    #    no-entailment-declared case is a no-op regardless. Tracked via
    #    the same _apply_and_track() helper as the "before rules" pass,
    #    for the same reason: excluded from the returned inference graph
    #    below.
    #
    # 2. result.conforms/report_graph/report_text above only ever reflect
    #    the state BEFORE the global rules pass (and before this second
    #    entailment pass too) - global-rule-produced triples were never
    #    actually validated at all. Re-validate the now-complete out_data
    #    once more, with the plain "validation" mode (not "rules" -
    #    rules have already run; re-running iterate_rules here would be
    #    wasteful and risks double-applying a non-idempotent rule), and
    #    use *this* call's conformance result instead - so conforms/
    #    report_graph genuinely cover the complete evaluation graph.

    _apply_and_track(
        lambda: apply_entailment(out_data, normalized_shapes, ont_graph, inplace=True, inference=inference_option)
    )

    final_options = resolve_mode_options("validation", overrides=kwargs)
    result = validate(
        out_data,
        normalized_shapes,
        ont_graph,
        mode="validation",
        **final_options,
    )

    # RulesResult.inferred_graph is strictly the SHACL 1.2 Inference Rules
    # spec's own "inference graph" - just the triples rule execution
    # itself produced (shape-attached sh:rule, global sh:SPARQLRule/
    # sh:RuleSet, and sh:sourceRule provenance reifiers). Neither the
    # original base triples (the caller's own data_graph, never mutated -
    # see this function's own docstring) nor anything any entailment
    # regime added (entailment_triples, tracked above) are included:
    # entailment is purely a computational device for correct rule
    # matching and conformance checking, never persisted. conforms/
    # report_graph/report_text above are still computed over the complete
    # evaluation graph (base ∪ rules ∪ entailment), so correctness isn't
    # affected - only what this function returns in inferred_graph changes.
    inference_graph = type(out_data)()
    for prefix, ns in out_data.namespaces():
        inference_graph.bind(prefix, ns)
    for t in frozenset(out_data) - base_triples - entailment_triples:
        inference_graph.add(t)

    return RulesResult(
        inferred_graph=inference_graph,
        validation=result,
    )


_stringify_bnode_patch_status: bool | None = None


def _patch_stringify_for_native_backend_bnodes() -> bool:
    """Make pySHACL's own violation-report text generation work when a
    reported focus/value node is a blank node and the graph being reported
    on is backed by a remote SPARQLUpdateStore-style store (Oxigraph,
    Fuseki via ``StarLayerGraph(store=..., backend='rdf-1.2')``).

    A confirmed, real pySHACL defect, not anything of this project's own
    code: ``pyshacl.constraints.constraint_component.make_v_result_description``
    calls ``stringify_node(datagraph, focus_node)``, which for a BNode
    focus node calls ``find_node_named_graph(dataset, node)`` when
    ``datagraph`` is a ``rdflib.Dataset`` (pySHACL's own internal
    representation of a shapes/data graph, built directly around the same
    store - not a ``StarLayerGraph``, so none of that class's own
    backend-aware overrides apply here). ``find_node_named_graph``'s
    original implementation calls ``dataset.quads((node, None, None,
    None))`` - a bound-BNode query sent straight to the raw store, which
    for ``rdflib.plugins.stores.sparqlstore.SPARQLUpdateStore`` always
    raises ("SPARQLStore does not support BNodes!"), regardless of whether
    that specific node could actually be found. This is a separate,
    narrower issue than the ``StarLayerGraph._native_triples()`` bug fixed
    in ``starlayer.graph`` itself (a real correctness bug in bound-BNode
    *query results*) - this one only affects being able to *render a
    report* that names a blank node, not validation correctness.

    Fixed by wrapping ``find_node_named_graph``: try the original first
    (unmodified, zero behavior change for the overwhelmingly common
    in-memory case), and only on failure fall back to reconstructing each
    of the dataset's contexts as a real ``StarLayerGraph`` sharing the same
    store and identifier - that class's own ``.triples()`` already handles
    a bound BNode correctly (matching it back by label after querying the
    position as an ordinary free variable, rather than trying to serialize
    the BNode into the query text at all - see its own docstring), so
    routing through it here finds the right context safely. Mirrors the
    original's own subject-then-object search order and ``LookupError`` on
    a genuine miss.

    Idempotent and defensive like this file's other runtime patches -
    returns ``False`` without raising if pySHACL's internals don't match
    what this expects.
    """
    global _stringify_bnode_patch_status
    if _stringify_bnode_patch_status is not None:
        return _stringify_bnode_patch_status

    try:
        import pyshacl.rdfutil.stringify as _stringify_mod

        if getattr(_stringify_mod.find_node_named_graph, "_starlayer_shacl_native_bnode_patched", False):
            _stringify_bnode_patch_status = True
            return True

        _original_find_node_named_graph = _stringify_mod.find_node_named_graph

        def _patched_find_node_named_graph(dataset, node):
            try:
                return _original_find_node_named_graph(dataset, node)
            except Exception:
                pass

            from rdflib.term import Variable

            from starlayer.graph.backends.native import execute_select
            from starlayer.graph.graph.starlayer_graph import StarLayerGraph

            # Deliberately not dataset.contexts()/dataset.graph(id): rdflib's
            # own Dataset.contexts() unconditionally yields (and, via
            # .graph(), *creates*) the dataset's own default-graph context
            # first - store.add_graph() -> "CREATE GRAPH <...>" - which
            # Oxigraph answers with a 500 rather than tolerating (confirmed
            # live), a problem this patch would otherwise newly introduce
            # simply by reaching a code path the original implementation
            # never touched. A plain SELECT DISTINCT for graph names has no
            # such side effect.
            _vars, bindings = execute_select(
                dataset.store, "rdf-1.2", "SELECT DISTINCT ?g WHERE { GRAPH ?g { ?s ?p ?o } }"
            )
            graph_names = [row[Variable("g")] for row in bindings if Variable("g") in row]

            def _wrap(name):
                # name=None -> the store's default graph (a StarLayerGraph built
                # with no explicit identifier is scoped there, not to a GRAPH
                # block - and "GRAPH ?g" above can never enumerate it).
                if name is None:
                    return StarLayerGraph(store=dataset.store, backend="rdf-1.2")
                return StarLayerGraph(store=dataset.store, identifier=name, backend="rdf-1.2")

            def _graph_contains(name, pattern) -> bool:
                try:
                    return next(iter(_wrap(name).triples(pattern)), None) is not None
                except Exception:
                    return False

            # Named graphs first (unchanged behavior), the default graph last.
            candidates = [*graph_names, None]
            for name in candidates:
                if _graph_contains(name, (node, None, None)):
                    return _wrap(name)
            for name in candidates:
                if _graph_contains(name, (None, None, node)):
                    return _wrap(name)
            raise LookupError(f"Cannot find node {node} in any named graph or the default graph.")

        _patched_find_node_named_graph._starlayer_shacl_native_bnode_patched = True
        _stringify_mod.find_node_named_graph = _patched_find_node_named_graph
        _stringify_bnode_patch_status = True
    except Exception:
        _stringify_bnode_patch_status = False
    return _stringify_bnode_patch_status


_source_rule_buffer: contextvars.ContextVar[list[tuple[tuple, Any]] | None] = contextvars.ContextVar(
    "_source_rule_buffer", default=None
)

_source_rule_patch_status: bool | None = None


def _patch_rule_apply_for_source_rule_provenance() -> bool:
    """Apply a targeted patch enabling ``sh:sourceRule`` provenance tracking
    (SHACL 1.2 SPARQL Extensions section 8.7) for shape-attached ``sh:rule``s
    - the ones pySHACL's own ``pyshacl.rules.apply_rules()`` executes
    internally via ``advanced=True``. Unlike this file's other two runtime
    patches (``_patch_shape_validate_for_filter_shape``,
    ``_patch_rdflib_data_graph_clone_preserves_tt_adapter``), this isn't
    fixing a pySHACL bug - it's the only way to get per-rule triple
    attribution at all, since ``pyshacl.rules.apply_rules()`` calls each
    ``SHACLRule.apply()`` in a loop it owns, returning only an int
    (``n_modified``), with no hook or callback for "which triples did *this*
    rule just add."

    Wraps ``TripleRule.apply``/``SPARQLRule.apply`` (both subclass
    ``pyshacl.rules.shacl_rule.SHACLRule``, whose own ``apply`` is abstract -
    each subclass has its own real implementation, so both need wrapping
    individually) to diff ``data_graph`` immediately before/after the
    *original* call, recording ``(triple, self.node)`` for every triple that
    call added - into ``_source_rule_buffer``, a ``contextvars.ContextVar``
    rather than a plain module global, so a caller who didn't opt in (the
    default - the var holds ``None``) gets a pure no-op passthrough with zero
    behavior change, and concurrent/nested ``apply_rules()`` calls don't leak
    records into each other's buffers.

    The diff-and-record step only *records* - it never adds anything to
    ``data_graph`` itself. The actual ``sh:sourceRule``/``rdf:reifies``
    triples are materialized later, in one batch, only once all rule
    execution has completely finished (see ``_materialize_source_rule_provenance``
    and ``apply_rules``'s own use of this buffer) - satisfying the spec's
    "MUST NOT be visible to executing rules" requirement for the provenance
    triples themselves, while leaving the underlying rule-inferred data
    triples visible to later rules exactly as before (that part of pySHACL's
    behavior is untouched - only observed).

    Idempotent (each class's ``apply`` is tagged after wrapping and skipped
    on a repeat call) and defensive like this file's other two patches -
    returns ``False`` without raising if pySHACL's internals don't match
    what this expects, so the caller can decide how to react instead of a
    silent no-op or a confusing crash.

    Returns:
        ``True`` if both ``TripleRule.apply``/``SPARQLRule.apply`` are
        now wrapped (or already were, on a repeat call); ``False`` if
        pySHACL's internals didn't match what this patch expects, with
        neither class touched.
    """
    global _source_rule_patch_status
    if _source_rule_patch_status is not None:
        return _source_rule_patch_status

    try:
        from pyshacl.rules.sparql import SPARQLRule
        from pyshacl.rules.triple import TripleRule

        for rule_cls in (TripleRule, SPARQLRule):
            original_apply = rule_cls.apply
            if getattr(original_apply, "_starlayer_shacl_source_rule_patch", False):
                continue

            def _wrap(original: Any) -> Any:
                def _patched_apply(self, data_graph, focus_nodes=None, target_graph_identifier=None):
                    buffer = _source_rule_buffer.get()
                    if buffer is None:
                        return original(
                            self,
                            data_graph,
                            focus_nodes=focus_nodes,
                            target_graph_identifier=target_graph_identifier,
                        )
                    before = set(data_graph)
                    result = original(
                        self,
                        data_graph,
                        focus_nodes=focus_nodes,
                        target_graph_identifier=target_graph_identifier,
                    )
                    after = set(data_graph)
                    for item in after - before:
                        # `data_graph` may be a quad-based `rdflib.Dataset`
                        # under `advanced=True` (confirmed live - iterating
                        # one yields 4-tuples, not 3-tuples); keep only the
                        # triple portion regardless of which it is.
                        buffer.append((tuple(item[:3]), self.node))
                    return result

                _patched_apply._starlayer_shacl_source_rule_patch = True  # type: ignore[attr-defined]
                return _patched_apply

            rule_cls.apply = _wrap(original_apply)
        _source_rule_patch_status = True
    except Exception:
        _source_rule_patch_status = False

    return _source_rule_patch_status


def _materialize_source_rule_provenance(
    out_data: Any,
    adapter: TripleTermAdapter,
    records: list[tuple[tuple[Any, Any, Any], Any]],
    *,
    decode: bool,
) -> None:
    """Add one reifier per ``(triple, rule_node)`` record to ``out_data``,
    encoding SHACL 1.2 SPARQL Extensions section 8.7's ``sh:sourceRule``
    provenance shorthand in its fully-expanded form: ``_:id rdf:reifies
    <<( s p o )>> . _:id sh:sourceRule <rule> .`` Call only after all rule
    execution has completely finished - see ``_patch_rule_apply_for_source_rule_provenance``'s
    docstring for why.

    Builds the reifier's ``rdf:reifies`` object as a plain ``(s, p, o)``
    3-tuple rather than via ``adapter.term_factory`` directly: the adapter's
    own ``term_factory`` defaults to the fallback ``TripleTermValue`` (not a
    real ``rdflib.Node``) regardless of whether ``out_data`` actually is a
    ``StarLayerGraph`` - `TripleTermAdapter.for_starlayer_graph()` is what
    would set it to the real ``starlayer.graph`` ``TripleTerm``, but nothing
    here can assume that classmethod was used to build ``adapter``. A plain
    3-tuple sidesteps that mismatch: ``StarLayerGraph.add()``'s own
    ``_coerce_tt`` explicitly recognizes "a tuple/TripleTerm" as inline
    triple-term shorthand in any node position (see its docstring), so this
    matches ``out_data``'s actual representation unconditionally, the same
    convention ``TripleTermAdapter._encode_node`` documents and relies on
    elsewhere in this codebase.

    Args:
        out_data: The working data graph to add each reifier to.
        adapter: Used to decode every term (subject/predicate/object and
            the rule node) back to ``out_data``'s own representation
            when ``decode=True``.
        records: ``(triple, rule_node)`` pairs - one per triple that
            some rule's ``apply()`` call produced, paired with the node
            identifying the rule that produced it.
        decode: ``True`` for records captured from pySHACL's own
            internal, URI-encoded execution (shape-attached
            ``sh:rule``s, captured via the ``TripleRule``/
            ``SPARQLRule.apply()`` patch) - every term, including the
            rule node itself, is decoded back through ``adapter``
            first, so the reifier's terms match ``out_data``'s own
            representation (the same ``adapter.decode_graph(encoded_data)``
            call that produced ``out_data`` in the first place).
            ``False`` for records already in ``out_data``'s own terms
            (the global ``sh:SPARQLRule`` pass, which queries the
            already-decoded ``out_data`` directly - nothing to decode).
    """
    for (s, p, o), rule_node in records:
        if decode:
            s = adapter.decode_term(s)
            p = adapter.decode_term(p)
            o = adapter.decode_term(o)
            rule_node = adapter.decode_term(rule_node)
        reifier = BNode()
        out_data.add((reifier, _RDF_REIFIES, (s, p, o)))
        out_data.add((reifier, SH.sourceRule, rule_node))


_layer_patch_status: bool | None = None


def _patch_rules_apply_for_layer_and_run_once() -> bool:
    """Apply a targeted patch enabling ``sh:layer``/``sh:runOnce`` (SHACL 1.2
    SPARQL Extensions section 8.2.4/8.2.6) for shape-attached ``sh:rule``s -
    and, as of the ``sh:expectedPredicate`` addition below, also the one
    hook point every rule-execution call (layered or not) passes through
    exactly once, used for that predicate's ``sh:defaultValue`` materialization.
    Despite the function name, this patch is now the single entry point for
    two related-but-distinct SHACL 1.2 SPARQL Extensions rule features - see
    ``_materialize_expected_predicates`` below for why it lives here rather
    than as a separate wrap of ``TripleRule.apply``/``SPARQLRule.apply``.

    pySHACL's own ``pyshacl.rules.apply_rules`` (called from
    ``pyshacl/validator.py`` under ``advanced=True``) processes shapes
    *sequentially* - shape A's own rules run to their own independent
    fixpoint, then shape B's, in ``shape.order`` order - with no notion of
    a shared cross-shape execution stage at all. The spec's layer model
    ("a SHACL rules engine will iterate over all rules in the same layer
    before moving to the next layer") is a *global* fixpoint across every
    rule in a layer regardless of which shape it's attached to - which
    pySHACL's per-shape loop cannot express: a shape processed later can
    never see a same-layer rule's triples from a shape processed earlier
    within one shared iteration, and there is no way for two rules on two
    different shapes to be in the same fixpoint at all.

    Rather than reimplement rule matching/CONSTRUCT execution, this reuses
    pySHACL's own ``SHACLRule.apply()``/``.order``/``.deactivated`` (via
    ``gather_rules``'s already-built ``Shape -> [SHACLRule]`` dict) and only
    replaces the *orchestration loop* around it - see
    ``_run_layered_rules`` below.

    **Gated on actual use, not applied unconditionally**: switching every
    rule execution to a global per-layer fixpoint would be a real behavior
    change even for shapes graphs that never use ``sh:layer``/``sh:runOnce``
    at all (default layer 0 for everything still changes "per-shape
    sequential fixpoint" into "one shared cross-shape fixpoint" - same
    predicates fire, but the exact interleaving/timing of *when* a
    same-layer-0 rule on one shape sees another same-layer-0 rule's output
    could differ). To keep zero behavior change for the existing test
    baseline, the patched function checks whether the shapes graph actually
    declares ``sh:layer``/``sh:runOnce`` anywhere and, if not, delegates
    straight to pySHACL's original, completely unmodified loop - the new
    native loop only ever runs for shapes graphs that opt into this SHACL
    1.2 vocabulary.

    **Known, deliberate limitation - not extended to global (unattached)
    ``sh:SPARQLRule``s.** ``starlayer.shacl``'s own ``_global_sparql_rule_triples``/
    ``_global_sparql_rules`` pass (rules with no ``sh:rule`` edge from any
    shape) runs as a separate pass *after* ``validate()`` returns entirely,
    unrelated to this patch or to pySHACL's own rule loop. A global rule
    that declares ``sh:layer``/``sh:runOnce`` is not read by either engine
    and always executes exactly once, in its existing position after every
    shape-attached rule has finished - fully unifying the two execution
    paths into one shared cross-shape-and-global layered fixpoint was
    judged out of scope for this change.

    Patches ``pyshacl.validator``'s own module-level ``apply_rules`` name
    (bound there via ``from .rules import apply_rules`` at that module's
    top) rather than ``pyshacl.rules.apply_rules`` itself - pySHACL's only
    call site (inside its ``Validator`` class, under ``advanced['rules']``)
    resolves a bare name at call time via the *calling* module's own
    globals, so reassigning the name in ``pyshacl.rules`` would not affect an
    already-imported reference in ``pyshacl.validator``. This is the only
    call site starlayer.shacl's own ``validate()``/``apply_rules()`` reaches
    (via ``from pyshacl import validate``, i.e. ``pyshacl.entrypoints.validate``
    -> ``Validator`` - not ``pyshacl.shacl_rules()``/``RuleExpandRunner``,
    a separate, unrelated pySHACL entrypoint this codebase doesn't use).

    Idempotent and defensive like this file's other three runtime patches -
    returns ``False`` without raising if pySHACL's internals don't match
    what this expects.
    """
    global _layer_patch_status
    if _layer_patch_status is not None:
        return _layer_patch_status

    try:
        import pyshacl.validator as _pyshacl_validator_module

        original_apply_rules = _pyshacl_validator_module.apply_rules
        if getattr(original_apply_rules, "_starlayer_shacl_layer_patch", False):
            _layer_patch_status = True
            return True

        def _patched_apply_rules(executor, shapes_rules, data_graph, focus_nodes=None):
            temp_triples = _materialize_expected_predicates(shapes_rules, data_graph)
            needs_native = any(
                list(rule.shape.sg.objects(rule.node, SH.layer))
                or list(rule.shape.sg.objects(rule.node, SH.runOnce))
                for rules in shapes_rules.values()
                for rule in rules
            )
            try:
                if not needs_native:
                    return original_apply_rules(executor, shapes_rules, data_graph, focus_nodes=focus_nodes)
                return _run_layered_rules(executor, shapes_rules, data_graph, focus_nodes)
            finally:
                # sh:expectedPredicate's own derived triples are only ever
                # meant to be visible *during* rule execution, not part of
                # its permanent output - see _materialize_expected_predicates'
                # docstring for the concrete W3C fixture evidence this is
                # based on, not just a spec-text inference.
                for triple in temp_triples:
                    data_graph.remove(triple)
                # sh:tempTriple (section 8.5) - rules may CONSTRUCT triples
                # that should be visible to *later* rules in the same
                # execution but never appear in the final output. Must run
                # after all rule execution in this call has fully finished
                # (same requirement, same timing as the sh:expectedPredicate
                # strip just above) - see _strip_temp_triples' own docstring.
                _strip_temp_triples(data_graph)

        _patched_apply_rules._starlayer_shacl_layer_patch = True  # type: ignore[attr-defined]
        _pyshacl_validator_module.apply_rules = _patched_apply_rules
        _layer_patch_status = True
    except Exception:
        _layer_patch_status = False

    return _layer_patch_status


def _run_layered_rules(executor: Any, shapes_rules: dict, data_graph: Any, focus_nodes: Any) -> int:
    """Native replacement for ``pyshacl.rules.apply_rules``, used only once
    ``_patch_rules_apply_for_layer_and_run_once`` has confirmed the shapes
    graph actually uses ``sh:layer``/``sh:runOnce`` - see that function's
    docstring for the full design rationale.

    Groups every rule (across every shape, flattened - not per-shape like
    pySHACL's original loop) by its own ``sh:layer`` value (default 0,
    ``xsd:integer``), executes layers in ascending numeric order, and
    within each layer runs every ``sh:runOnce`` rule exactly once (sorted by
    ``sh:order``, deactivated ones skipped, "before the other rules in the
    same layer" per spec) followed by every "iterating" rule together in one
    shared fixpoint (not a per-shape one) - mirrors pySHACL's own
    ``iterate_rules``/``RULES_ITERATE_LIMIT``/overflow-error semantics
    exactly, just applied across the whole layer instead of one shape.

    Rule/shape insertion order is used as a stable secondary sort key
    alongside ``sh:order`` (the spec doesn't define tie-breaking for equal
    order values) - deterministic given a fixed ``shapes_rules`` dict, but
    not itself spec-mandated.
    """
    from pyshacl.errors import ReportableRuntimeError
    from pyshacl.rules import RULES_ITERATE_LIMIT

    all_rules = [rule for rules in shapes_rules.values() for rule in rules]

    def _layer_of(rule: Any) -> int:
        values = list(rule.shape.sg.objects(rule.node, SH.layer))
        if not values:
            return 0
        return int(values[0])

    def _run_once_of(rule: Any) -> bool:
        values = list(rule.shape.sg.objects(rule.node, SH.runOnce))
        return bool(values) and bool(values[0])

    layers: dict[int, list[tuple[int, Any]]] = {}
    for idx, rule in enumerate(all_rules):
        layers.setdefault(_layer_of(rule), []).append((idx, rule))

    total_modified = 0
    for layer_key in sorted(layers.keys()):
        entries = layers[layer_key]
        run_once_entries = sorted((e for e in entries if _run_once_of(e[1])), key=lambda e: (e[1].order, e[0]))
        iterating_entries = sorted((e for e in entries if not _run_once_of(e[1])), key=lambda e: (e[1].order, e[0]))

        for _, rule in run_once_entries:
            if rule.deactivated:
                continue
            total_modified += rule.apply(data_graph, focus_nodes=focus_nodes)

        iterate_limit = int(RULES_ITERATE_LIMIT)
        while True:
            if iterate_limit < 1:
                raise ReportableRuntimeError(
                    f"SHACL Shape Rule iteration exceeded iteration limit of {RULES_ITERATE_LIMIT}."
                )
            iterate_limit -= 1
            this_modified = 0
            for _, rule in iterating_entries:
                if rule.deactivated:
                    continue
                this_modified += rule.apply(data_graph, focus_nodes=focus_nodes)
            if this_modified > 0:
                total_modified += this_modified
                if executor.iterate_rules:
                    continue
                break
            break

    return total_modified


def _materialize_expected_predicates(shapes_rules: dict, data_graph: Any) -> list[tuple[Any, Any, Any]]:
    """``sh:expectedPredicate`` (SHACL 1.2 SPARQL Extensions section 8.2.7,
    "Expected Derived Triples"): both the ``sh:defaultValue`` and
    ``sh:values`` halves.

    Per spec: a rule declaring ``sh:expectedPredicate ex:p`` expects that,
    before it executes, the *derived* triples for ``ex:p`` - computed via
    ``sh:defaultValue``/``sh:values`` on every non-deactivated property
    shape using ``ex:p`` as ``sh:path`` - are already materialized in the
    data graph. ``sh:values`` here is SHACL 1.2 Core's *validation-time*
    computed-value mechanism (``sh:select``/``sh:sparqlExpr`` on an ordinary
    property shape - already implemented, see ``_compute_sh_values``/
    ``_patch_shape_value_nodes_for_sh_values`` above) - **not** the same
    predicate name's unrelated, separately-tracked, genuinely unimplemented
    ``sh:PropertyRule``/``sh:values`` shorthand (a `sh:rule`-construction
    mechanism, see that row in ``docs/shacl12-gap-matrix.md``'s Core
    changelog table) - the two happen to share a name but are otherwise
    distinct, and this function only touches the former. ``sh:defaultValue``
    itself had *zero* runtime behavior anywhere in this codebase or in
    pySHACL before this function was first added - it was previously only
    ever documented, never materialized as a real triple.

    **Returns the materialized triples so the caller can remove them again
    once rule execution finishes**: these derived triples are transient,
    visible only *during* rule execution, never part of ``apply_rules()``'s
    permanent output - consistent with ``sh:defaultValue``'s well-established
    SHACL Core meaning as a validation-time *virtual* value, not something a
    conformant processor permanently asserts. The W3C SHACL 1.2 test suite's
    own ``expectedPredicate-example`` fixture confirms this: its expected-
    result list includes only the rule's own CONSTRUCTed conclusions
    (``ex:isSmall``), never the ``ex:area`` values this function computes to
    let the rule's WHERE clause evaluate correctly.

    Called unconditionally, once, from ``_patched_apply_rules`` above -
    before either the original or the native layered rule loop begins -
    rather than as a third wrap of ``TripleRule.apply``/``SPARQLRule.apply``
    (alongside the one ``_patch_rule_apply_for_source_rule_provenance``
    already installs for ``sh:sourceRule``). A second independent wrap of
    those same two methods would create a real, hard-to-predict ordering
    dependency: which patch ends up outermost depends on whether
    ``apply_rules(include_source_rule_provenance=True)`` or a plain
    ``validate()``/``apply_rules()`` call patches ``TripleRule.apply``/
    ``SPARQLRule.apply`` *first* in a given process (each patch, once
    applied, is permanent and order-preserving for the rest of the
    process) - if the source-rule-provenance wrap ends up outermost, its
    before/after diff would incorrectly attribute these materialized
    triples to whichever rule happened to trigger materialization, as if
    that rule had inferred them itself. This function's call site is a
    *single*, always-applied wrap (this file's own layer/run-once patch),
    so there is no second wrap to race against and no ordering question to
    resolve - deliberately chosen over the per-rule hook point for this
    reason, not merely for convenience.
    """
    all_rules = [rule for rules in shapes_rules.values() for rule in rules]
    if not all_rules:
        return []

    shapes_graph = all_rules[0].shape.sg.graph
    shapes_graph_wrapper = all_rules[0].shape.sg
    predicates: set = set()
    for rule in all_rules:
        predicates.update(shapes_graph.objects(rule.node, SH.expectedPredicate))
    if not predicates:
        return []

    return _materialize_default_value_triples(data_graph, shapes_graph, shapes_graph_wrapper, predicates)


def _materialize_default_value_triples(
    data_graph: Any, shapes_graph: Any, shapes_graph_wrapper: Any, predicates: set
) -> list[tuple[Any, Any, Any]]:
    """For each predicate, and for every non-deactivated property shape in
    ``shapes_graph`` whose ``sh:path`` is that predicate, add derived
    ``(focus, predicate, value)`` triples to ``data_graph`` for every
    target/focus node of that property shape that has no existing value for
    the predicate - preferring an ``sh:values``-computed value when the
    property shape declares one and it produces at least one result,
    falling back to a plain ``sh:defaultValue`` otherwise (matching the
    ``expectedPredicate-example`` fixture's own worked case: a rectangle
    with real width/height gets its area computed via ``sh:values``, one
    with neither falls back to ``sh:defaultValue``'s constant). Never
    overwrites or duplicates an already-asserted value, per
    ``sh:defaultValue``'s own spec-defined semantics ("used when no other
    values are present for a property").

    A property shape's own "target/focus nodes" are, per ordinary SHACL
    Core semantics, the target nodes of whatever node shape(s) reference it
    via ``sh:property`` (the common case - see the SHACL 1.2 SPARQL
    Extensions spec's own worked ``ex:RectangleShape``/
    ``ex:RectangleShape-area`` example) - plus, for completeness, the
    property shape's own targets if it happens to declare ``sh:target*``
    directly (a rarer, but spec-legitimate, top-level-property-shape case).

    Args:
        data_graph: The data graph to materialize derived triples into.
        shapes_graph: The raw shapes graph (used for ``.triples()``/
            ``.objects()`` lookups of ``sh:path``/``sh:deactivated``/
            ``sh:values``/``sh:defaultValue``).
        shapes_graph_wrapper: pySHACL's own ``ShapesGraph`` wrapper, needed
            to resolve a property shape node to a real ``Shape`` object for
            ``sh:values`` computation via ``lookup_shape_from_node``.
        predicates: The set of ``sh:expectedPredicate`` IRIs to materialize
            derived triples for.

    Returns:
        Every ``(focus, predicate, value)`` triple actually added, so the
        caller can strip them again once rule execution finishes - see
        ``_materialize_expected_predicates``'s docstring for why.
    """
    added: list[tuple[Any, Any, Any]] = []
    for path in predicates:
        for prop_shape in {s for s, _, _ in shapes_graph.triples((None, SH.path, path))}:
            deactivated = next(iter(shapes_graph.objects(prop_shape, SH.deactivated)), None)
            if deactivated is not None and bool(deactivated):
                continue

            values_node = next(iter(shapes_graph.objects(prop_shape, SH.values)), None)
            default_values = list(shapes_graph.objects(prop_shape, SH.defaultValue))
            if values_node is None and not default_values:
                continue

            focus_nodes: set = set(_shape_target_nodes(data_graph, shapes_graph, prop_shape))
            for host_shape, _, _ in shapes_graph.triples((None, SH.property, prop_shape)):
                focus_nodes.update(_shape_target_nodes(data_graph, shapes_graph, host_shape))

            real_prop_shape = None
            if values_node is not None:
                try:
                    real_prop_shape = shapes_graph_wrapper.lookup_shape_from_node(prop_shape)
                except (AttributeError, KeyError):
                    # lookup_shape_from_node is a plain dict lookup with no
                    # lazy-build fallback of its own - at this early point in
                    # pyshacl.validate()'s pipeline (advanced['rules'] runs
                    # before shape validation), a property shape reachable
                    # only via sh:property may not be cached yet even though
                    # the outer node shape (reached via gather_rules, which
                    # is how this function got a Shape at all) already is.
                    # _build_node_shape_cache() is itself incremental/
                    # idempotent (skips any node already present, see its own
                    # source) - safe to call again rather than only on an
                    # empty cache, unlike the narrower `if len(...) < 1` guard
                    # pyshacl.ShapesGraph.shapes itself uses for its own,
                    # different (whole-cache-empty) case.
                    try:
                        shapes_graph_wrapper._build_node_shape_cache()
                        real_prop_shape = shapes_graph_wrapper.lookup_shape_from_node(prop_shape)
                    except (AttributeError, KeyError):
                        real_prop_shape = None

            for focus in focus_nodes:
                if any(True for _ in data_graph.triples((focus, path, None))):
                    continue

                computed: list = []
                if real_prop_shape is not None:
                    computed = _compute_sh_values(real_prop_shape, values_node, data_graph, focus)

                if computed:
                    for value in computed:
                        triple = (focus, path, value)
                        data_graph.add(triple)
                        added.append(triple)
                elif default_values:
                    default_computed = _compute_sh_default_value(default_values[0], data_graph, shapes_graph_wrapper, focus)
                    if default_computed:
                        triple = (focus, path, default_computed[0])
                        data_graph.add(triple)
                        added.append(triple)

    return added


def _strip_temp_triples(data_graph: Any) -> None:
    """``sh:tempTriple`` (SHACL 1.2 SPARQL Extensions section 8.5,
    "Temporary Triples") - a genuinely new predicate, per the W3C SHACL 1.2
    test suite's own ``temp-triples-example`` fixture.

    Per spec: "It is sometimes useful for inference rules to produce
    triples that are only visible during the execution of other rules but
    do not end up in the final inferences. A temporary triple is an
    inferred triple for which the inference graph contains a reifier with
    the value ``sh:tempTriple true``. Temporary triples and their reifiers
    are visible to executing rules" - but must not survive into the final
    output. Unlike the spec's own worked example (which uses RDF-1.2's
    inline reifier-annotation shorthand, ``$this ex:offspring ?offspring
    {| sh:tempTriple true |}``), the W3C test suite's own fixture uses the
    fully-expanded longhand form directly in its CONSTRUCT template
    (``?reifier rdf:reifies ?tt . ?reifier sh:tempTriple true .``, with
    ``?tt`` built via ``BIND (TRIPLE(...) AS ?tt)``) - both forms produce
    the identical reifier triples once a rule's CONSTRUCT has executed, so
    this function only needs to look for that fully-expanded shape,
    regardless of which syntax a given rule used to produce it.

    Called once, after all rule execution for a given ``apply_rules()``
    call has completely finished (both the shape-attached path this
    function's own call site sits in, and - not yet extended, see below -
    the separate global-rules path), same timing requirement as
    ``sh:expectedPredicate``'s own transient materialization: temp triples
    must stay visible to *executing* rules (so no interleaved stripping
    mid-execution), but never appear in ``apply_rules()``'s permanent
    output.

    The reified value (the ``rdf:reifies`` object) is the pySHACL-internal
    *encoded* form - ``TripleTermAdapter``'s content-addressed
    ``urn:starlayer:tt:HASH`` URI,
    not a real ``TripleTerm`` - since ``TRIPLE()`` runs against ``data_graph``
    at this point in ``pyshacl.validate()``'s pipeline, which is already
    adapter-encoded (the outer ``StarShaclSchema.validate()`` call
    encodes before ever handing off to pySHACL). ``_get_tt_adapter``/
    ``adapter.decode_term`` (the same helpers ``native_components.py`` uses
    for every other reifier lookup in this codebase) resolve it back to the
    real ``(s, p, o)`` - a plain ``(s, p, o)`` 3-tuple is also accepted as a
    fallback for robustness, matching the convention this codebase's own
    reifier creation elsewhere (``_materialize_source_rule_provenance``)
    uses when no adapter is present at all.

    Removes the reified triple itself, plus every triple with the reifier
    node as its own subject (not just the two this codebase's own
    ``sh:sourceRule`` materialization would produce) - "temporary triples
    *and their reifiers*" (plural, spec's own wording) reads as "the whole
    reifier node," not just its two defining triples, in case a rule
    asserted anything else about that same reifier.

    **Known, deliberate limitation**: not wired into the separate global
    (unattached ``sh:SPARQLRule``) rules path (``_global_sparql_rule_triples``)
    - no currently-known fixture combines a global rule with
    ``sh:tempTriple``; same category of gap as that function's own
    documented ``sh:expectedPredicate`` limitation, for the same reason
    (no concrete case to build/test against yet).
    """
    reifiers = {
        s
        for s, _, o in data_graph.triples((None, SH.tempTriple, None))
        if bool(o.value if hasattr(o, "value") else o)
    }
    if not reifiers:
        return

    adapter = _get_tt_adapter(data_graph)

    for reifier in reifiers:
        for _, _, reified in list(data_graph.triples((reifier, _RDF_REIFIES, None))):
            if adapter is not None:
                reified = adapter.decode_term(reified)
            if hasattr(reified, "subject") and hasattr(reified, "predicate") and hasattr(reified, "object"):
                data_graph.remove((reified.subject, reified.predicate, reified.object))
            elif isinstance(reified, tuple) and len(reified) == 3:
                data_graph.remove(reified)
        for triple in list(data_graph.triples((reifier, None, None))):
            data_graph.remove(triple)


def _shape_target_nodes(data_graph: Any, shapes_graph: Any, shape_node: Any) -> set:
    """Minimal SHACL Core target resolution (``sh:targetNode``/
    ``sh:targetClass``/``sh:targetSubjectsOf``/``sh:targetObjectsOf``),
    operating directly via ``.triples()``/``.objects()`` on whatever raw
    graph objects ``sh:expectedPredicate`` materialization runs against -
    deliberately not ``starlayer.shacl.engine.target_nodes`` (which normalizes
    both graphs into a fresh ``StarLayerGraph`` copy on every call - real
    overhead, and unproven against the quad/``RdfLibDataGraph``-wrapped
    graph shapes this specific, pySHACL-internal execution point actually
    hands over). SHACL 1.2's newer target types (``sh:targetWhere``,
    implicit class targets, ``sh:shape``) are already flattened to plain
    ``sh:targetNode`` triples by ``StarShaclSchema.
    _augment_shapes_with_new_target_types`` earlier in ``validate()``'s own
    pipeline, well before any rule ever executes - so this narrower,
    Core-only set is already complete by the time this runs.
    """
    targets: set = set()
    targets.update(shapes_graph.objects(shape_node, SH.targetNode))
    for cls in shapes_graph.objects(shape_node, SH.targetClass):
        targets.update(s for s, _, _ in data_graph.triples((None, RDF.type, cls)))
    for pred in shapes_graph.objects(shape_node, SH.targetSubjectsOf):
        targets.update(s for s, _, _ in data_graph.triples((None, pred, None)))
    for pred in shapes_graph.objects(shape_node, SH.targetObjectsOf):
        targets.update(o for _, _, o in data_graph.triples((None, pred, None)))
    return targets


_filter_shape_patch_status: bool | None = None


def _patch_shape_validate_for_filter_shape() -> bool:
    """Apply a targeted compatibility shim for the confirmed pySHACL bug in
    ``sh:filterShape`` (see ``docs/upstream-issues/pyshacl-upstream-issues.md``): patches
    ``pyshacl.shape.Shape.validate`` to detect the broken 2-argument calling
    convention pySHACL's own ``nodes_from_node_expression`` filterShape
    branch uses (``filter_shape.validate(data_graph, node)``) and adapt it to
    the correct one (a ``SHACLExecutor`` first, ``target_graph`` second,
    ``focus`` as a keyword) - a real fix for a real bug, not a workaround
    that changes any SHACL semantics. Every correctly-formed call (a real
    ``SHACLExecutor`` as the first argument) falls straight through to the
    original method completely unchanged.

    Idempotent (safe to call many times - patches at most once per process)
    and defensive: if pySHACL's internals don't match what this shim
    expects (e.g. a future/past version with a different ``Shape.validate``
    signature or without ``SHACLExecutor``), returns ``False`` without
    raising, so the caller can fall back to a clear hard-fail instead of a
    silent no-op or a confusing crash.

    This patches process-global state (``pyshacl.shape.Shape.validate``),
    not something scoped to starShacl's own call sites - any other code in
    the same process calling pySHACL directly is affected too, harmlessly,
    since the shim is a strict superset of the original behavior.

    Returns:
        ``True`` if the patch is installed (or was already, in an earlier
        call); ``False`` if pySHACL's internals didn't match what this shim
        expects, in which case nothing was patched.
    """
    global _filter_shape_patch_status
    if _filter_shape_patch_status is not None:
        return _filter_shape_patch_status

    try:
        import pyshacl.shape
        from pyshacl.pytypes import SHACLExecutor

        original_validate = pyshacl.shape.Shape.validate
        if getattr(original_validate, "_starlayer_shacl_filter_shape_patch", False):
            _filter_shape_patch_status = True
            return True

        def _patched_validate(self, executor_or_graph, target_graph_or_focus=None, focus=None, **kwargs):
            if isinstance(executor_or_graph, SHACLExecutor):
                return original_validate(self, executor_or_graph, target_graph_or_focus, focus=focus, **kwargs)
            # The broken calling convention: filter_shape.validate(data_graph, node).
            return original_validate(self, SHACLExecutor(), executor_or_graph, focus=target_graph_or_focus)

        _patched_validate._starlayer_shacl_filter_shape_patch = True  # type: ignore[attr-defined]
        pyshacl.shape.Shape.validate = _patched_validate
        _filter_shape_patch_status = True
    except Exception:
        _filter_shape_patch_status = False

    return _filter_shape_patch_status


_rdflib_data_graph_clone_patch_status: bool | None = None


def _patch_rdflib_data_graph_clone_preserves_tt_adapter() -> bool:
    """Apply a targeted compatibility shim for a confirmed pySHACL bug: under
    ``advanced=True``, ``pyshacl.validator.Validator`` unconditionally clones
    the data graph ("Forcing clone of DataGraph because advanced mode is
    enabled" - needed so SHACL-AF rules don't mutate the caller's original
    graph). ``RdfLibDataGraph.clone()`` builds the new copy via
    ``pyshacl.rdfutil.clone.clone_graph()``, which produces a *plain*
    ``rdflib.Graph``/``Dataset`` - it has no notion of, and so drops,
    starShacl's own ``_SparqlAwareEncodedGraph`` wrapper and its
    ``_tt_adapter`` back-reference (see ``adapters.py``), even though the
    clone's actual triples (the flattened ``urn:starlayer:tt:HASH``
    encoding) are faithfully copied.

    This breaks ``ReifierShapeConstraintComponent`` - and any other
    triple-term-aware check - specifically when ``advanced=True`` (needed
    for ``sh:expression``/``sh:rule`` elsewhere, and therefore always passed
    by ``tests/w3c_shacl12/test_w3c_validate.py`` since it can't tell in
    advance which fixtures need it): without ``_tt_adapter``,
    ``native_components.py``'s ``_get_tt_adapter()``/``_encode_key()`` fall
    back to treating a ``(focus, path, value)`` tuple as an un-encodable raw
    value, which can never match the graph's actual encoded
    ``rdf:reifies`` triples - so a reifier check against a cloned graph
    silently finds no reifiers at all and reports vacuous conformance. The
    same helper backs ``sh:TripleTerm`` node-kind recognition
    (``_is_encoded_triple_term``), so this affects more than just
    ``sh:reifierShape`` - anything relying on triple-term encoding
    awareness, combined with ``advanced=True``.

    Patches ``pyshacl.graph_abstraction.RdfLibDataGraph.clone`` two ways:

    1. When ``self.impl`` carries a ``_tt_adapter`` and the caller didn't
       already supply a ``destination``, pre-constructs a fresh
       ``starlayer.shacl.adapters._SparqlAwareEncodedGraph`` (the *same
       class* ``self.impl`` already is in real ``validate()``/
       ``apply_rules()`` usage - see that class's own docstring) and passes
       it as ``clone_graph()``'s own ``target_graph`` parameter -
       ``clone_graph``'s ``target_graph`` is optional, and every triple is
       copied via ordinary ``g.add(t)`` either way, so this is a real,
       already-existing extension point, not something requiring pySHACL's
       own code to change.

       A plain ``StarLayerGraph()`` is not a substitute here: ``self.impl``
       in real usage is ``_SparqlAwareEncodedGraph``, not ``StarLayerGraph``
       directly (the adapter wraps the *encoded* graph, decoding to a real
       ``StarLayerGraph`` only inside its own ``.query()`` override), and
       that override - the thing that actually routes a query through
       ``StarLayerGraph``'s triple-term-aware SPARQL 1.2 lowering (parsing
       via ``starlayer.sparql.prepare_query_12``, lowering ``TRIPLE()``/
       ``SUBJECT()``/``PREDICATE()``/``OBJECT()``/``isTRIPLE()`` to plain
       SPARQL 1.1 encoding-triple patterns *before* rdflib's raw evaluator
       ever runs) - lives on the ``_SparqlAwareEncodedGraph`` *class itself*,
       not on the ``_tt_adapter`` attribute alone. Point 2 below (bolting
       ``_tt_adapter`` onto whatever bare ``rdflib.Graph`` pySHACL's own
       ``clone_graph()`` produces by default) is not equivalent to this: the
       attribute is present, but ``.query()`` is still inherited unchanged
       from plain ``rdflib.Graph``, so it never redirects at all.
       ``starlayer.sparql/grammar12.py`` deliberately binds no raw ``evalfn`` for
       ``TRIPLE``/``SUBJECT``/``PREDICATE``/``OBJECT``/``isTRIPLE`` - by
       design, since ``StarLayerGraph.query()``'s lowering is supposed to
       intercept them first - so querying a clone that lost this routing
       crashes with ``Exception: Weird - _eval got a CompValue without
       evalfn!``/``Exception: What do I do with this CompValue?`` the moment
       one of them is used - see
       ``tests/integration/test_sparql_shacl_integration.py``'s triple-term-
       accessor cases, which exercise exactly this once ``advanced=True``
       stopped being a rare opt-in.
    2. Copies ``_tt_adapter`` from the pre-clone ``.impl`` onto the post-
       clone ``.impl`` when present (still needed for a caller-supplied
       ``destination`` that doesn't already carry one) - lets
       ``native_components.py``'s
       ``_get_tt_adapter()``/``_encode_key()`` (``sh:reifierShape`` and
       ``sh:TripleTerm`` node-kind recognition, which read the attribute
       directly rather than going through ``.query()``) keep working against
       the clone.

    Both are a strict superset of the original behavior - a no-op for any
    graph without a ``_tt_adapter`` (i.e. every use of pySHACL directly, or
    of starShacl without triple-term data).

    Idempotent and defensive like ``_patch_shape_validate_for_filter_shape``
    - returns ``False`` without raising if pySHACL's internals don't match
    what this shim expects, so the caller can decide how to react instead of
    a silent no-op or a confusing crash.
    """
    global _rdflib_data_graph_clone_patch_status
    if _rdflib_data_graph_clone_patch_status is not None:
        return _rdflib_data_graph_clone_patch_status

    try:
        import pyshacl.graph_abstraction as ga

        original_clone = ga.RdfLibDataGraph.clone
        if getattr(original_clone, "_starlayer_shacl_tt_adapter_patch", False):
            _rdflib_data_graph_clone_patch_status = True
            return True

        def _patched_clone(self, destination=None, identifier=None):
            adapter = getattr(self.impl, "_tt_adapter", None)
            if destination is None and adapter is not None:
                from starlayer.shacl.adapters import _SparqlAwareEncodedGraph

                # Pre-construct the *same* class .impl already is
                # (_SparqlAwareEncodedGraph, not a plain rdflib.Graph) as
                # clone_graph()'s own target_graph, so it gets populated by
                # copying triples in rather than pySHACL's own default of
                # always building a bare rdflib.Graph(). Passing `adapter`
                # through the constructor (not just bolting it on after, the
                # original fix below) matters: .query()'s own routing to a
                # decoded StarLayerGraph lives on this *class*, not on the
                # adapter attribute alone - bolting _tt_adapter onto a plain
                # rdflib.Graph instance (the previous fix) leaves .query()
                # still inherited unchanged from rdflib.Graph, so it silently
                # never redirects at all.
                destination = _SparqlAwareEncodedGraph(adapter=adapter)
            cloned = original_clone(self, destination, identifier)
            if adapter is not None:
                cloned.impl._tt_adapter = adapter
            return cloned

        _patched_clone._starlayer_shacl_tt_adapter_patch = True  # type: ignore[attr-defined]
        ga.RdfLibDataGraph.clone = _patched_clone
        _rdflib_data_graph_clone_patch_status = True
    except Exception:
        _rdflib_data_graph_clone_patch_status = False

    return _rdflib_data_graph_clone_patch_status


def _compute_sh_values(shape: Any, values_node: Any, target_graph: Any, focus_node: Any) -> list:
    """The computed value set for one focus node, per a property shape's
    ``sh:values`` (SHACL 1.2 Core's "new ``sh:values``" mechanism, a
    `sh:PropertyRule`-adjacent but distinct feature).

    Three forms, tried in order: a full ``sh:select`` query (using its own
    single projected variable, whatever it's named); a single
    ``sh:sparqlExpr`` scalar expression (wrapped into a one-row ``SELECT
    (<expr> AS ?_computed) WHERE {}``), both evaluated with ``$this``/
    ``?this`` bound to ``focus_node`` exactly the way ``sh:sparql``
    constraints already do, reusing pySHACL's own ``SPARQLQueryHelper``
    wholesale (prefix collection via ``sh:prefixes``, ``$this`` pre-binding)
    rather than reimplementing either; or, if ``values_node`` is neither of
    those but is itself a node expression (e.g. ``sparql:multiply ( [
    shnex:pathValues ex:width ] [ shnex:pathValues ex:height ] )`` - the
    SHACL 1.2 SPARQL Extensions spec's own worked ``sh:expectedPredicate``
    example, confirmed via the W3C test suite's ``expectedPredicate-example``
    fixture), evaluated via ``starlayer.shacl.node_expressions.eval_expr`` -
    the same node-expression evaluator ``shnex:``/``sparql:`` forms use
    everywhere else in this codebase, not a separate implementation.

    Args:
        shape: The property shape carrying ``values_node``, used for its
            ``sg`` (shapes graph wrapper) when delegating to pySHACL's
            ``SPARQLQueryHelper``.
        values_node: The object of the shape's ``sh:values`` triple - a
            ``sh:select``/``sh:sparqlExpr``-bearing node, or a node
            expression.
        target_graph: The data graph to evaluate the query/expression
            against.
        focus_node: The focus node bound to ``$this``/``?this`` (query
            forms) or passed as the expression's own focus node.

    Returns:
        The non-``None`` computed values, in whatever order the query/
        expression produced them.
    """
    from pyshacl.helper import get_query_helper_cls

    select_vals = list(shape.sg.graph.objects(values_node, SH.select))
    expr_vals = list(shape.sg.graph.objects(values_node, SH.sparqlExpr))
    if select_vals:
        query_text = str(select_vals[0])
    elif expr_vals:
        query_text = f"SELECT ({expr_vals[0]} AS ?_computed) WHERE {{}}"
    else:
        from starlayer.shacl.node_expressions import eval_expr

        try:
            return [v for v in eval_expr(values_node, focus_node, target_graph, shape.sg) if v is not None]
        except Exception:
            return []

    SPARQLQueryHelper = get_query_helper_cls()
    query_helper = SPARQLQueryHelper(shape, values_node, query_text)
    query_helper.collect_prefixes()

    init_binds, sparql_text = query_helper.pre_bind_variables(focus_node)
    sparql_text = query_helper.apply_prefixes(sparql_text)
    try:
        rows = list(target_graph.query(sparql_text, initBindings=init_binds))
    except Exception:
        return []
    return [row[0] for row in rows if row[0] is not None]


def _compute_sh_default_value(default_value_node: Any, target_graph: Any, sg: Any, focus_node: Any) -> list:
    """SHACL 1.2 Core's own "Value Nodes of Property Shapes" algorithm treats
    ``sh:defaultValue`` exactly like ``sh:values`` for evaluation purposes -
    "add the output nodes of evalExpr(d, data graph, focus node, {})" - so a
    ``sh:defaultValue`` can be a full node expression (e.g. ``[
    shnex:pathValues ex:firstName ]``, falling back to a sibling property
    when the target one is missing), not just a plain constant. A plain
    ``Literal``/``URIRef`` constant still evaluates to itself via
    ``eval_expr``'s own constant-node handling, so this is a strict superset
    of "just read the raw RDF object", not a special case for the
    node-expression form alone. A plain object-lookup read of
    ``sh:defaultValue`` would be wrong for the node-expression form
    specifically: it would add the blank node itself as a bogus "value"
    rather than evaluating it.

    Args:
        default_value_node: The object of the shape's ``sh:defaultValue``
            triple - a constant or a node expression.
        target_graph: The data graph to evaluate the expression against.
        sg: The shapes graph wrapper (pySHACL's ``ShapesGraph``), passed
            through to ``eval_expr``.
        focus_node: The focus node to evaluate the expression relative to.

    Returns:
        The non-``None`` evaluated default value(s).
    """
    from starlayer.shacl.node_expressions import eval_expr

    try:
        return [v for v in eval_expr(default_value_node, focus_node, target_graph, sg) if v is not None]
    except Exception:
        return []


_value_nodes_patch_status: bool | None = None


def _patch_shape_value_nodes_for_sh_values() -> bool:
    """Apply a targeted extension for SHACL 1.2 Core's new ``sh:values``: a
    property shape's own effective value set can be *computed* (via
    ``sh:select``/``sh:sparqlExpr``, see ``_compute_sh_values``) instead of
    read from the data graph via ``sh:path`` - a mechanism pySHACL 0.40.1
    has no notion of at all (confirmed via the same predicate-registry grep
    approach used for every other new-predicate gap in this file: no
    ``SH_values``/``sh:values`` reference anywhere in pySHACL's codebase).

    Patches ``pyshacl.shape.Shape.value_nodes`` - the single method every
    constraint component (``sh:datatype``, ``sh:hasValue``, etc.) already
    calls generically to get its focus-to-values mapping - rather than
    special-casing each constraint component individually, so every *other*
    constraint on a ``sh:values``-carrying shape runs completely unmodified
    against the resulting value set. Falls straight through to the original
    method for every shape without ``sh:values``.

    **UNIONS with the real, path-based values - does not replace them.**
    SHACL 1.2 Core's "Value Nodes of Property Shapes" section gives an
    exact, unambiguous three-step algorithm: "Add all nodes in the data
    graph that can be reached from the focus node with the path mapping of
    p. If e is the value of sh:values ..., then *add* the output nodes of
    evalExpr(e, ...). If the set is still empty and d is the value of
    sh:defaultValue ..., then add the output nodes of evalExpr(d, ...)."
    Both sh:path's real values and sh:values's computed values are
    unconditionally *added* to the same set - sh:defaultValue is the only
    one of the three gated on "if the set is still empty".

    Step 3 (``sh:defaultValue``) applies whenever the shape declares it, not
    only alongside ``sh:values`` - a plain property shape with only
    ``sh:defaultValue`` still gets inspected for it. See
    ``tests/integration/test_sh_values.py``'s ``TestDefaultValueFallback``
    for the regression coverage, including the negative cases (a real
    stored value, or a non-empty ``sh:values`` computation, both correctly
    take priority and skip the default).

    Idempotent and defensive like the other patches in this module -
    returns ``False`` without raising if pySHACL's internals don't match
    what this shim expects.

    Returns:
        ``True`` if the patch is applied (or was already applied by an
        earlier call), ``False`` if pySHACL's internals didn't match what
        this shim expects.
    """
    global _value_nodes_patch_status
    if _value_nodes_patch_status is not None:
        return _value_nodes_patch_status

    try:
        import pyshacl.shape

        original_value_nodes = pyshacl.shape.Shape.value_nodes
        if getattr(original_value_nodes, "_starlayer_shacl_values_patch", False):
            _value_nodes_patch_status = True
            return True

        def _patched_value_nodes(self, target_graph, focus, sparql_mode=False, debug=False):
            original = original_value_nodes(self, target_graph, focus, sparql_mode=sparql_mode, debug=debug)
            if not self.is_property_shape:
                return original
            values_node = next(iter(self.sg.graph.objects(self.node, SH.values)), None)
            default_values = list(self.sg.graph.objects(self.node, SH.defaultValue))
            if values_node is None and not default_values:
                return original
            focus_list = focus if isinstance(focus, (tuple, list, set)) else [focus]
            result = {}
            for f in focus_list:
                # Steps 1+2 (path values, sh:values) are unconditionally
                # unioned; step 3 (sh:defaultValue) only kicks in "if the set
                # is still empty" - see this function's own docstring for the
                # exact three-step algorithm quoted from SHACL 1.2 Core.
                values = set(original.get(f, ()))
                if values_node is not None:
                    values |= set(_compute_sh_values(self, values_node, target_graph, f))
                if not values and default_values:
                    for default_value_node in default_values:
                        values |= set(_compute_sh_default_value(default_value_node, target_graph, self.sg, f))
                result[f] = values
            return result

        _patched_value_nodes._starlayer_shacl_values_patch = True  # type: ignore[attr-defined]
        pyshacl.shape.Shape.value_nodes = _patched_value_nodes
        _value_nodes_patch_status = True
    except Exception:
        _value_nodes_patch_status = False

    return _value_nodes_patch_status


_deactivated_expr_registry: contextvars.ContextVar[dict[Any, Any] | None] = contextvars.ContextVar(
    "_deactivated_expr_registry", default=None
)

_deactivated_focus_nodes_patch_status: bool | None = None


def _patch_shape_focus_nodes_for_deactivated_expression() -> bool:
    """Implement SHACL 1.2 Core's actual ``sh:deactivated``-as-node-expression
    semantics: "Let expr be the value of sh:deactivated in a shape. If
    evalExpr(expr, data graph, focus node, {}) produces true as its only
    output node, the shape is called deactivated" - evaluated once **per
    focus node**, from Core's own "Deactivating Shapes and Constraints"
    section (not the node-expr document, which only mentions
    ``sh:deactivated`` once in passing with no worked example or evaluation
    algorithm of its own). A node-expression-valued ``sh:deactivated`` is
    therefore a per-target filter, not a global per-shape on/off switch
    evaluated once with no focus node at all - a `shnex:var "focusNode"`
    -referencing expression must vary per target, the way Core's own
    definition requires, not deactivate the whole shape uniformly.

    Patches ``pyshacl.shape.Shape.focus_nodes`` - the method
    ``Shape.validate()`` calls to resolve a shape's own targets into a
    concrete focus-node set whenever ``validate()`` isn't given an explicit
    ``focus=`` restriction (the overwhelming common case - confirmed via
    ``pyshacl/validator.py``'s own single call site, ``s.validate(executor,
    g, focus=on_focus_nodes)``, where ``on_focus_nodes`` is ``None`` unless
    a caller explicitly passes ``focus_nodes=`` to ``validate()``). For each
    node the original method would return, evaluates the shape's
    registered expression (looked up via ``_deactivated_expr_registry``,
    populated by ``StarShaclSchema._strip_deactivated_node_expressions``
    for the duration of one ``validate()`` call) with that node as the
    focus node, and excludes it if the expression evaluates to exactly
    ``true`` - every other node proceeds to normal constraint evaluation
    unaffected. A node the expression can't evaluate (raises) is kept
    (fails open - treated as active), matching this module's general
    "shallow but broad" tolerance for malformed input elsewhere.

    Idempotent and defensive like the other patches in this module -
    returns ``False`` without raising if pySHACL's internals don't match
    what this shim expects. A no-op whenever ``_deactivated_expr_registry``
    is unset/empty (the default), so this patch is harmless to apply
    unconditionally once any caller needs it.
    """
    global _deactivated_focus_nodes_patch_status
    if _deactivated_focus_nodes_patch_status is not None:
        return _deactivated_focus_nodes_patch_status

    try:
        import pyshacl.shape
        from rdflib import Literal as _Literal

        from starlayer.shacl.node_expressions import eval_expr

        original_focus_nodes = pyshacl.shape.Shape.focus_nodes
        if getattr(original_focus_nodes, "_starlayer_shacl_deactivated_expr_patch", False):
            _deactivated_focus_nodes_patch_status = True
            return True

        def _patched_focus_nodes(self, data_graph, debug=False):
            result = original_focus_nodes(self, data_graph, debug=debug)
            registry = _deactivated_expr_registry.get()
            if not registry:
                return result
            expr = registry.get(self.node)
            if expr is None:
                return result
            kept = set()
            for node in result:
                try:
                    computed = eval_expr(expr, node, data_graph, self.sg)
                except Exception:
                    kept.add(node)
                    continue
                is_true = len(computed) == 1 and next(iter(computed)) in (_Literal(True), True)
                if not is_true:
                    kept.add(node)
            return kept

        _patched_focus_nodes._starlayer_shacl_deactivated_expr_patch = True  # type: ignore[attr-defined]
        pyshacl.shape.Shape.focus_nodes = _patched_focus_nodes
        _deactivated_focus_nodes_patch_status = True
    except Exception:
        _deactivated_focus_nodes_patch_status = False

    return _deactivated_focus_nodes_patch_status


_expression_constraint_scope_patch_status: bool | None = None


def _patch_expression_constraint_for_value_scope() -> bool:
    """Fix two real bugs in pySHACL's own ``ExpressionConstraint.
    _evaluate_expression`` (``pyshacl/constraints/advanced/__init__.py``),
    found against the SHACL 1.2 Node Expressions spec's own
    "sh:expression" TEXTUAL DEFINITION - ``evalExpr(expr, data graph,
    focusNode, {value: v})`` - and its worked example (which uses
    ``shnex:var "value"`` directly):

    1. pySHACL's own call, ``nodes_from_node_expression(expr, v, data_graph,
       self.shape.sg)``, passes the *value* node ``v`` positionally where
       ``focus_node`` belongs - the real shape focus node ``f`` (available
       in the very same loop, via ``f_v_dict.items()``) is never passed to
       node-expression evaluation at all. ``shnex:var "focusNode"`` inside
       ``sh:expression`` on a property shape therefore returns the *value*
       node, not the real focus node, whenever they differ.
    2. Scope is never seeded with ``"value"`` at all, so ``shnex:var
       "value"`` - used directly in the spec's own IBAN worked example
       under this same section, a real, spec-exampled pattern, not an edge
       case - always resolves to unbound.

    Patches ``pyshacl.constraints.advanced.ExpressionConstraint.
    _evaluate_expression`` to call ``starlayer.shacl.node_expressions.eval_expr``
    directly (which already delegates to pySHACL's own old-form handling
    for every expression that isn't ``shnex:``/``sparql:``-tagged, so this
    is a strict superset, not a narrowing) with the correct
    ``focus_node=f`` and ``scope={"focusNode": f, "value": v}`` - fixing
    both bugs at once, since they share the same one-line root cause.
    Everything else in the method (message collection, report building via
    ``self.make_v_result``) is reproduced unchanged from the original.

    Idempotent and defensive like the other patches in this module -
    returns ``False`` without raising if pySHACL's internals don't match
    what this shim expects.
    """
    global _expression_constraint_scope_patch_status
    if _expression_constraint_scope_patch_status is not None:
        return _expression_constraint_scope_patch_status

    try:
        import pyshacl.constraints.advanced as _advanced_mod
        from rdflib import Literal as _Literal

        from starlayer.shacl.node_expressions import eval_expr

        ExpressionConstraint = _advanced_mod.ExpressionConstraint
        original = ExpressionConstraint._evaluate_expression
        if getattr(original, "_starlayer_shacl_value_scope_patch", False):
            _expression_constraint_scope_patch_status = True
            return True

        def _patched_evaluate_expression(self, data_graph, f_v_dict, expr):
            reports = []
            non_conformant = False
            messages = list(self.shape.sg.objects(expr, _advanced_mod.SH_message))
            if len(messages):
                messages = [next(iter(messages))]
            else:
                messages = None
            for f, value_nodes in f_v_dict.items():
                for v in value_nodes:
                    n_set = eval_expr(expr, f, data_graph, self.shape.sg, scope={"focusNode": f, "value": v})
                    if (
                        isinstance(n_set, (list, set))
                        and len(n_set) == 1
                        and next(iter(n_set)) in (_Literal(True), True)
                    ):
                        continue
                    non_conformant = True
                    reports.append(
                        self.make_v_result(
                            data_graph, f, value_node=v, source_constraint=expr, extra_messages=messages
                        )
                    )
            return non_conformant, reports

        _patched_evaluate_expression._starlayer_shacl_value_scope_patch = True  # type: ignore[attr-defined]
        ExpressionConstraint._evaluate_expression = _patched_evaluate_expression
        _expression_constraint_scope_patch_status = True
    except Exception:
        _expression_constraint_scope_patch_status = False

    return _expression_constraint_scope_patch_status


def _default_validate(**kwargs: Any) -> tuple[bool, Graph, str]:
    from pyshacl import validate

    return validate(**kwargs)


def _is_starlayer_graph(value: Any) -> bool:
    try:
        from starlayer.graph.graph.starlayer_graph import StarLayerGraph
    except ImportError:
        return False

    return isinstance(value, StarLayerGraph)


def _graph_contains_triple_terms(graph: Any) -> bool:
    if graph is None:
        return False

    try:
        triple_terms = getattr(graph, "triple_terms", None)
        if triple_terms is None:
            return False

        for _ in triple_terms():
            return True
    except TypeError:
        return False

    return False


def _inject_shapes_graph_subclass_triples(
    data_graph: Any, shacl_graph: Any, *, enabled: bool
) -> tuple[Any, set[tuple[Any, Any, Any]]]:
    """When ``enabled`` (the ``rdfs_subclass_reasoning_includes_shapes_graph``
    ``validate()`` option), copy the shapes graph's own ``rdfs:subClassOf``
    triples into a copy of ``data_graph``, so pySHACL-visible code that walks
    ``rdfs:subClassOf`` (e.g. ``sh:rootClass``'s registered constraint
    component - see ``starlayer.shacl/native_components.py``) sees them without
    needing a separate channel to the shapes graph. The caller removes
    exactly the returned ``injected`` triples from the encoded copy handed to
    pySHACL immediately after validation, so they never leak into
    caller-visible output.
    """
    if not enabled or shacl_graph is None:
        return data_graph, set()

    subclass_triples = set(shacl_graph.triples((None, RDFS.subClassOf, None)))
    injected = {triple for triple in subclass_triples if triple not in data_graph}
    if not injected:
        return data_graph, set()

    augmented = type(data_graph)()
    for triple in data_graph:
        augmented.add(triple)
    for triple in injected:
        augmented.add(triple)
    return augmented, injected


def _resolve_shapes_graph_imports(
    shacl_graph: Any,
    *,
    graph_loader: Callable[[Any], Any | None],
) -> Any:
    """Extend ``shacl_graph`` with its transitive ``owl:imports`` closure per
    the SHACL 1.2 Core spec.

    2026-10-08: now a thin wrapper around ``StarLayerGraph.resolve_imports()``,
    which generalizes the identical algorithm (``^owl:versionIRI?/owl:imports``,
    cycle-safe, fully transitive) this function used to implement itself -
    see that method's own docstring for the full account, and
    ``starlayer/graph/CLAUDE.md``'s dated entry for why the general version
    exists. Pure delegation, confirmed via the existing
    ``test_shapes_graph_imports.py`` suite (versionIRI redirect, no-loader,
    unresolvable-import, self-import cycle, multi-hop-without-versionIRI) -
    every behavior there is unchanged; ``shacl_graph`` is already a
    ``StarLayerGraph`` by the time this runs (normalized earlier in
    ``validate()``), so calling the method directly needs no extra
    conversion.

    Retrieval itself is delegated to ``graph_loader`` (given an import IRI,
    returns a parsed graph, or ``None`` if it can't be resolved) - this
    library doesn't dictate a network-fetching policy; an unresolvable
    import is simply skipped rather than raising.

    Args:
        shacl_graph: The shapes graph to extend - already a
            ``StarLayerGraph`` by the time this runs.
        graph_loader: Given an import IRI, returns the parsed graph to merge
            in, or ``None`` if it can't be resolved.

    Returns:
        ``shacl_graph`` extended with its transitive ``owl:imports``
        closure.
    """
    return shacl_graph.resolve_imports(loader=graph_loader, mode="full")


def _is_subclass_of_or_self(graph: Any, node: Any, target_class: Any, extra_graph: Any | None = None) -> bool:
    """Whether ``node`` is ``target_class`` itself, or a transitive
    ``rdfs:subClassOf`` subclass of it in ``graph`` (the reflexive-transitive
    ``rdfs:subClassOf*`` relationship the SHACL 1.2 Core spec's "SHACL
    Subclass" definition describes).

    ``extra_graph``, when given, is also consulted for ``rdfs:subClassOf``
    triples alongside ``graph`` - the spec's "SHACL Type" definition notes
    implementations MAY be parameterized to look these up in the shapes graph
    in addition to the data graph (Issue 185); callers pass the shapes graph
    here only when a caller opts into that behavior.
    """
    if node == target_class:
        return True

    seen = {node}
    frontier = [node]
    while frontier:
        current = frontier.pop()
        superclasses = set(o for _, _, o in graph.triples((current, RDFS.subClassOf, None)))
        if extra_graph is not None:
            superclasses |= set(o for _, _, o in extra_graph.triples((current, RDFS.subClassOf, None)))
        for superclass in superclasses:
            if superclass == target_class:
                return True
            if superclass not in seen:
                seen.add(superclass)
                frontier.append(superclass)
    return False


def _find_genuine_report_node(report_graph: Any) -> Any | None:
    """Find the real, freshly-generated top-level ``sh:ValidationReport``
    node in ``report_graph``, disambiguating it from any *incidental*
    ``sh:ValidationReport``-typed node that happens to be copied into the
    report as some unrelated result's ``sh:value``/``sh:focusNode``.

    This ambiguity is real, not hypothetical: a fixture using
    ``sht:dataGraph <>`` (the W3C SHACL 1.2 test suite's own format) treats
    its own ``mf:result [ a sh:ValidationReport ; ... ]`` expected-result
    block as ordinary data. If some violation's value/focus node is that
    block, pySHACL's report construction copies its triples into the output
    report, producing a second ``sh:ValidationReport``-typed node.

    Every post-processing step that needs "the report node" must use this, not
    "the first node of that type": picking the wrong one is not harmless. One
    step relabels the chosen node (``_relabel_validation_report_node``), which
    rewrites its identity everywhere it appears - so choosing the incidental
    copy renames a *data* node inside the results, after which the violation
    no longer names the original node. That made ``sh:targetWhere`` (which
    reads focus nodes back out of a nested report) intermittently treat a
    non-conforming node as conforming, depending on graph iteration order.

    The genuine report is told apart structurally: it is a fresh node that
    nothing in the report refers to, whereas an incidental copy was pulled in
    specifically because a result's ``sh:focusNode`` / ``sh:value`` (or other
    data) refers to it. The one reference the genuine report may have is this
    library's own ``<graph> sh:validationReport <report>`` link. If that still
    leaves more than one candidate, the one with the most ``sh:result`` is
    taken, with a deterministic tie-break, so the answer never depends on
    iteration order.

    Args:
        report_graph: The validation report graph to search.

    Returns:
        The real top-level ``sh:ValidationReport`` node, or ``None`` if
        ``report_graph`` has none at all.
    """
    candidates = sorted({s for s, _, _ in report_graph.triples((None, RDF.type, SH.ValidationReport))}, key=str)
    if len(candidates) <= 1:
        return candidates[0] if candidates else None

    def only_linked_to(node: Any) -> bool:
        return all(p == SH.validationReport for _, p, _ in report_graph.triples((None, None, node)))

    roots = [n for n in candidates if only_linked_to(n)]
    if len(roots) == 1:
        return roots[0]
    pool = roots or candidates
    return max(pool, key=lambda n: (len(list(report_graph.objects(n, SH.result))), str(n)))


def _rule_set_members(shapes_graph: Any, rule_set: Any) -> frozenset:
    """Every rule node that's a member of ``rule_set``, including
    transitively via ``sh:includesRuleSet`` (SHACL 1.2 SPARQL Extensions
    section 8.2.1).

    Plain worklist/visited-set graph reachability over ``sh:includesRuleSet``
    edges, collecting each visited rule set's own ``sh:hasRule`` members
    along the way - correct regardless of cycles or traversal order without
    needing ``_cross_node_reachable_shapes``'s own fixed-point-vs-DFS
    care (see that function's docstring): this is a single ordinary BFS/DFS
    reachability walk from one root with a visited set, not that function's
    multi-root bottom-up memoization pattern, which is the specific shape
    that was unsound under cycles - a plain visited-set traversal has no
    equivalent problem.
    """
    seen_rule_sets: set[Any] = set()
    worklist = [rule_set]
    members: set[Any] = set()
    while worklist:
        rs = worklist.pop()
        if rs in seen_rule_sets:
            continue
        seen_rule_sets.add(rs)
        members.update(shapes_graph.objects(rs, SH.hasRule))
        for included in shapes_graph.objects(rs, SH.includesRuleSet):
            if included not in seen_rule_sets:
                worklist.append(included)
    return frozenset(members)


_rule_set_filter: contextvars.ContextVar[frozenset | None] = contextvars.ContextVar(
    "_rule_set_filter", default=None
)

_rule_set_patch_status: bool | None = None


def _patch_rule_apply_for_rule_set_filtering() -> bool:
    """Apply a targeted patch enabling ``rule_set=`` selection
    (``StarShaclSchema.apply_rules``) for shape-attached ``sh:rule``s -
    the ones pySHACL's own ``pyshacl.rules.apply_rules()`` executes
    internally via ``advanced=True``, with no parameter of its own to
    restrict which rules run.

    Independent of, and structurally identical to,
    ``_patch_rule_apply_for_source_rule_provenance`` (wraps the same two
    classes, same idempotent-tagging discipline, same
    ``contextvars.ContextVar``-gated no-op-by-default passthrough when no
    caller has opted in) - deliberately a *separate* patch/tag/contextvar
    rather than folded into that one, so this file's one working, already-
    tested provenance feature isn't put at risk to add a second, unrelated
    one. The two compose correctly regardless of which patches first in a
    given process: each wraps whatever ``rule_cls.apply`` already is at the
    moment it patches and unconditionally delegates to it, so a rule
    filtered out here never reaches the real underlying ``SHACLRule.apply``
    (and therefore is invisible to a provenance-diff wrapper on either side
    of it - it observes zero triples added, which is correct either way).

    Unlike the provenance patch (which only *observes*), this one is a real
    behavior change when a caller opts in (``rule_set is not None``): a
    rule node not in the current ``_rule_set_filter`` value's membership set
    returns immediately (0 modified, no triples added) instead of running.

    Returns:
        ``True`` if the patch is applied (or was already applied by an
        earlier call), ``False`` if pySHACL's internals didn't match what
        this shim expects.
    """
    global _rule_set_patch_status
    if _rule_set_patch_status is not None:
        return _rule_set_patch_status

    try:
        from pyshacl.rules.sparql import SPARQLRule
        from pyshacl.rules.triple import TripleRule

        for rule_cls in (TripleRule, SPARQLRule):
            original_apply = rule_cls.apply
            if getattr(original_apply, "_starlayer_shacl_rule_set_patch", False):
                continue

            def _wrap(original: Any) -> Any:
                def _patched_apply(self, data_graph, focus_nodes=None, target_graph_identifier=None):
                    allowed = _rule_set_filter.get()
                    if allowed is not None and self.node not in allowed:
                        return 0
                    return original(
                        self,
                        data_graph,
                        focus_nodes=focus_nodes,
                        target_graph_identifier=target_graph_identifier,
                    )

                _patched_apply._starlayer_shacl_rule_set_patch = True  # type: ignore[attr-defined]
                return _patched_apply

            rule_cls.apply = _wrap(original_apply)
        _rule_set_patch_status = True
    except Exception:
        _rule_set_patch_status = False

    return _rule_set_patch_status


def _global_sparql_rules(shacl_graph: Any, allowed_rule_nodes: frozenset | None = None) -> list:
    """SHACL 1.2's "global" (shape-independent) ``sh:SPARQLRule`` nodes - a
    rule node that exists standalone, never referenced by any shape's own
    ``sh:rule`` property, meant to execute once against the whole graph
    regardless of target matching. Confirmed via pySHACL's own
    ``pyshacl/rules/__init__.py::gather_rules()``, which discovers rules
    exclusively through ``shacl_graph.subject_objects(SH_rule)`` (i.e.
    reachable from some shape) - a standalone rule node has no incoming
    ``sh:rule`` edge and is invisible to it, silently never executing.
    Scoped to ``sh:SPARQLRule`` only (not ``sh:TripleRule``): the one W3C
    SHACL 1.2 test suite fixture this was found via
    (``sparql/rules/global-symmetric.ttl``) only exercises ``sh:SPARQLRule``,
    and ``sh:TripleRule``'s subject/predicate/object node expressions are
    ordinarily evaluated relative to ``$this``/a focus node - a "global"
    application with no focus node at all has no obvious semantics to
    apply without a concrete test case to confirm against.

    ``allowed_rule_nodes``: when given (a caller opted into ``rule_set=``
    on ``apply_rules()``), restricts the result to rules also in this set -
    see ``_rule_set_members``. ``None`` (the default) means no restriction,
    identical to this function's pre-``rule_set`` behavior.
    """
    referenced = set(shacl_graph.objects(None, SH.rule))
    rule_nodes = [r for r in shacl_graph.subjects(RDF.type, SH.SPARQLRule) if r not in referenced]
    if allowed_rule_nodes is not None:
        rule_nodes = [r for r in rule_nodes if r in allowed_rule_nodes]
    return rule_nodes


def _global_sparql_rule_triples(
    data_graph: Any, shacl_graph: Any, allowed_rule_nodes: frozenset | None = None
) -> list[tuple[tuple, Any]]:
    """Every ``(triple, rule_node)`` pair produced by running every global
    ``sh:SPARQLRule`` (see ``_global_sparql_rules``) to completion against
    ``data_graph``, honoring ``sh:layer``/``sh:runOnce``/``sh:order``
    (SHACL 1.2 SPARQL Extensions section 8.2.4-8.2.6) and iterating each
    layer's non-run-once rules to a real fixpoint - a rule can depend on
    another global rule's own output (e.g. two RDFS-entailment-style rules
    chained together, `?a rdf:type ?x . ?x rdfs:subClassOf ?y` depending on
    a *different* rule's `rdf:type` inference), so a single CONSTRUCT pass
    per rule is not enough. Every global rule implicitly sits at layer 0 by
    the spec's own stated default, and the layered/fixpoint loop applies
    unconditionally, regardless of whether the shapes graph declares
    ``sh:layer``/``sh:runOnce`` at all.

    **Mutates ``data_graph`` directly as it goes** (not just at the end),
    both because later rules in the same/a later layer need to see earlier
    rules' output, and because a fixpoint can't be detected without
    materializing each round's triples before running the next one. The
    caller no longer needs to (and, since this already added everything,
    should not redundantly) add the returned triples itself - see
    ``apply_rules``'s own comment at its call site.

    Honors ``sh:deactivated`` on the rule node itself. Prefix resolution
    reuses ``_ambient_shapes_graph_prefixes`` (see that function's own
    docstring) since a global rule, having no shape of its own, can't carry
    an explicit ``sh:prefixes`` reference at all.

    Each triple is paired with the rule node that produced it - consumed
    both for the caller's own bookkeeping and for ``sh:sourceRule``
    provenance (section 8.7) when a caller opts in.

    **Known, deliberate limitation**: ``sh:expectedPredicate`` materialization
    (``_materialize_expected_predicates``) is not wired into this path - it
    only runs once, up front, for shape-attached rules. No currently-known
    fixture combines a global rule with ``sh:expectedPredicate``; if one
    ever needs it, the fix is straightforward (call
    ``_materialize_default_value_triples`` here too, predicates gathered
    from these rule nodes) but wasn't added speculatively.
    """
    from pyshacl.errors import ReportableRuntimeError
    from pyshacl.rules import RULES_ITERATE_LIMIT

    rule_nodes = _global_sparql_rules(shacl_graph, allowed_rule_nodes=allowed_rule_nodes)
    if not rule_nodes:
        return []

    ambient_prefixes = _ambient_shapes_graph_prefixes(shacl_graph)
    prefix_text = "".join(f"PREFIX {p}: <{ns}>\n" for p, ns in ambient_prefixes.items())

    def _is_deactivated(rule_node: Any) -> bool:
        deactivated = next(iter(shacl_graph.objects(rule_node, SH.deactivated)), None)
        return deactivated is not None and bool(deactivated.value if hasattr(deactivated, "value") else deactivated)

    def _layer_of(rule_node: Any) -> int:
        values = list(shacl_graph.objects(rule_node, SH.layer))
        return int(values[0]) if values else 0

    def _run_once_of(rule_node: Any) -> bool:
        values = list(shacl_graph.objects(rule_node, SH.runOnce))
        return bool(values) and bool(values[0])

    def _order_key(rule_node: Any) -> tuple[float, int]:
        values = list(shacl_graph.objects(rule_node, SH.order))
        order = float(values[0]) if values else 0.0
        return (order, rule_nodes.index(rule_node))

    def _apply_one(rule_node: Any) -> list[tuple[tuple, Any]]:
        if _is_deactivated(rule_node):
            return []
        construct_vals = list(shacl_graph.objects(rule_node, SH.construct))
        if not construct_vals:
            return []
        query_text = prefix_text + str(construct_vals[0])
        produced: list[tuple[tuple, Any]] = []
        try:
            # starlayer.graph.backends.native.native_query() sends a query's
            # text to the remote endpoint with no graph-scoping of its own
            # (see that function's own docstring) - an unscoped CONSTRUCT
            # like this one would silently match against the store's
            # separate, empty default graph rather than data_graph's own
            # named context. Confirmed live against both Oxigraph and
            # Fuseki: the identical query returns nothing run directly,
            # but the correct triples once explicitly scoped. Rather than
            # textually rewrite an arbitrary caller-authored CONSTRUCT
            # query to inject a GRAPH clause (fragile for anything beyond
            # a simple BGP - UNION/OPTIONAL/nested groups would need a
            # real SPARQL-aware rewrite), snapshot the native graph's
            # current triples into a local, in-memory StarLayerGraph (kept
            # as StarLayerGraph rather than a plain rdflib.Graph so SPARQL
            # 1.2 triple-term query syntax is still understood) and
            # evaluate the CONSTRUCT there instead - correct regardless of
            # query complexity, at the cost of one extra read per call.
            # The non-native (default in-memory) case is entirely
            # unaffected - same query, same target, as before.
            query_target = data_graph
            if getattr(data_graph, "_is_native", False):
                from starlayer.graph.graph.starlayer_graph import StarLayerGraph

                snapshot = StarLayerGraph()
                for t in data_graph:
                    snapshot.add(t)
                query_target = snapshot
            for triple in query_target.query(query_text):
                if triple not in data_graph:
                    produced.append((triple, rule_node))
        except Exception:
            return []
        for triple, _ in produced:
            data_graph.add(triple)
        return produced

    layers: dict[int, list[Any]] = {}
    for rule_node in rule_nodes:
        layers.setdefault(_layer_of(rule_node), []).append(rule_node)

    all_added: list[tuple[tuple, Any]] = []
    for layer_key in sorted(layers.keys()):
        entries = layers[layer_key]
        run_once_nodes = sorted((r for r in entries if _run_once_of(r)), key=_order_key)
        iterating_nodes = sorted((r for r in entries if not _run_once_of(r)), key=_order_key)

        for rule_node in run_once_nodes:
            all_added.extend(_apply_one(rule_node))

        iterate_limit = int(RULES_ITERATE_LIMIT)
        while True:
            if iterate_limit < 1:
                raise ReportableRuntimeError(
                    f"SHACL Shape Rule iteration exceeded iteration limit of {RULES_ITERATE_LIMIT}."
                )
            iterate_limit -= 1
            this_round: list[tuple[tuple, Any]] = []
            for rule_node in iterating_nodes:
                this_round.extend(_apply_one(rule_node))
            all_added.extend(this_round)
            if not this_round:
                break

    return all_added


def _transitive_subclasses(data_graph: Any, shacl_graph: Any, superclass: Any) -> set:
    """Every class transitively ``rdfs:subClassOf`` ``superclass``, searching
    both ``data_graph`` and ``shacl_graph`` (a class hierarchy can live in
    either - an ontology asserted alongside the data, or, as in the W3C
    SHACL 1.2 test suite's self-referential fixtures, in the same document
    that doubles as the shapes graph). Does not include ``superclass``
    itself - see the implicit-class-target call site, which unions it in
    separately.
    """
    result: set = set()
    frontier = [superclass]
    seen = {superclass}
    while frontier:
        current = frontier.pop()
        for graph in (data_graph, shacl_graph):
            for sub, _, _ in graph.triples((None, RDFS.subClassOf, current)):
                if sub not in seen:
                    seen.add(sub)
                    result.add(sub)
                    frontier.append(sub)
    return result


def _is_implicit_class_shape(shacl_graph: Any, shape_node: Any) -> bool:
    if not isinstance(shape_node, URIRef):
        # Per spec: a shape that is a SHACL instance of rdfs:Class but not
        # an IRI is ill-formed; only IRI shapes can use this mechanism.
        return False

    types = set(o for _, _, o in shacl_graph.triples((shape_node, RDF.type, None)))
    return RDFS.Class in types or SH.ShapeClass in types


def _collect_by_types_properties(shacl_graph: Any, shape_node: Any, visited: set) -> set:
    """The ``collectProperties(S)`` algorithm from the SHACL 1.2 Core spec's
    ``sh:closed sh:ByTypes`` definition: a node's own ``sh:property``/
    ``sh:path`` properties, plus (if it's itself a class) its superclasses'
    and sibling-shapes' properties, plus (if it's a node shape) properties
    of any shape it ``sh:node``-links to. ``visited`` guards against
    infinite loops on cyclic class hierarchies.
    """
    if shape_node in visited:
        return set()
    visited.add(shape_node)

    props: set = set()
    for prop in (o for _, _, o in shacl_graph.triples((shape_node, SH.property, None))):
        path = next((o for _, _, o in shacl_graph.triples((prop, SH.path, None))), None)
        if isinstance(path, URIRef):
            props.add(path)

    if _is_implicit_class_shape(shacl_graph, shape_node):
        for _, _, superclass in shacl_graph.triples((shape_node, RDFS.subClassOf, None)):
            props |= _collect_by_types_properties(shacl_graph, superclass, visited)
        for other_shape, _, _ in shacl_graph.triples((None, SH.targetClass, shape_node)):
            props |= _collect_by_types_properties(shacl_graph, other_shape, visited)

    if any(True for _ in shacl_graph.triples((shape_node, RDF.type, SH.NodeShape))):
        for _, _, linked in shacl_graph.triples((shape_node, SH.node, None)):
            props |= _collect_by_types_properties(shacl_graph, linked, visited)

    return props


def _is_shacl_list(graph: Any, node: Any) -> bool:
    """Per the SHACL 1.2 Core spec: a SHACL list is an IRI or blank node that
    is either ``rdf:nil`` (with no ``rdf:first``/``rdf:rest`` values of its
    own), or has exactly one ``rdf:first`` and one ``rdf:rest`` value that is
    itself a SHACL list, with no cycle through ``rdf:rest+``.
    """
    seen: set[Any] = set()
    current = node
    while True:
        if current == RDF.nil:
            has_first = any(True for _ in graph.triples((current, RDF.first, None)))
            has_rest = any(True for _ in graph.triples((current, RDF.rest, None)))
            return not has_first and not has_rest

        if current in seen:
            return False
        seen.add(current)

        firsts = tuple(o for _, _, o in graph.triples((current, RDF.first, None)))
        rests = tuple(o for _, _, o in graph.triples((current, RDF.rest, None)))
        if len(firsts) != 1 or len(rests) != 1:
            return False

        current = rests[0]


def _shacl_list_members(graph: Any, node: Any) -> list[Any]:
    """The members of a SHACL list, in order. Assumes ``_is_shacl_list`` is
    already true for ``node``.
    """
    members: list[Any] = []
    current = node
    while current != RDF.nil:
        first = next((o for _, _, o in graph.triples((current, RDF.first, None))), None)
        members.append(first)
        current = next((o for _, _, o in graph.triples((current, RDF.rest, None))), RDF.nil)
    return members
