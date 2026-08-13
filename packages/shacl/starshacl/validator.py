from __future__ import annotations

from typing import Any, Callable, Iterable

from rdflib import BNode, Graph, Literal, Namespace, URIRef
from rdflib.collection import Collection
from rdflib.namespace import OWL, RDF, RDFS

from starshacl.adapters import TripleTermAdapter, TripleTermGraph
from starshacl.engine import (
    ComponentRequest,
    build_report as native_build_report,
    evaluate_component as native_evaluate_component,
    normalize_graph_inputs,
    target_nodes as native_target_nodes,
)
from starshacl.native_components import (
    SHAPE_EXPECTING_PREDICATES,
    _ambient_shapes_graph_prefixes,
    ensure_shape_typed,
    register_native_components,
    shape_reference_nodes,
)
from starshacl.profiles import ValidationProfile, resolve_profile_options
from starshacl.results import ExecutionDiagnostics, RulesResult, ValidationResult
from starshacl.types import ensure_graph_mutable, is_dirlangstring_like


SH = Namespace("http://www.w3.org/ns/shacl#")
SHNEX = Namespace("http://www.w3.org/ns/shacl-node-expr#")
SPARQL_EXPR_NS = Namespace("http://www.w3.org/ns/sparql#")

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


class StarShaclValidator:
    """Wrapper service for SHACL validation/rules with triple-term adaptation."""

    def __init__(
        self,
        adapter: TripleTermAdapter | None = None,
        validate_fn: Callable[..., tuple[bool, Graph, str]] | None = None,
    ) -> None:
        self.adapter = adapter or TripleTermAdapter()
        self.validate_fn = validate_fn or _default_validate

    def target_nodes(
        self,
        *,
        data_graph: Any,
        shacl_graph: Any,
        shape_node: Any,
    ) -> tuple[Any, ...]:
        return native_target_nodes(data_graph=data_graph, shacl_graph=shacl_graph, shape_node=shape_node)

    def evaluate_component(
        self,
        *,
        component: Any,
        focus_node: Any,
        value_nodes: tuple[Any, ...],
        options: dict[str, Any] | None = None,
    ) -> Any:
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
        return native_build_report(events=events, graph_context=graph_context, options=options)

    def validate(
        self,
        data_graph: Any,
        shacl_graph: Any | None = None,
        ont_graph: Any | None = None,
        *,
        profile: str | ValidationProfile | None = None,
        decode_report: bool = True,
        rdfs_subclass_reasoning_includes_shapes_graph: bool = False,
        shapes_graph_loader: Callable[[Any], Any | None] | None = None,
        meta_shapes_extra: Iterable[Any] = (),
        **kwargs: Any,
    ) -> ValidationResult:
        self.adapter.reset_diagnostics()

        register_native_components()
        _patch_rdflib_data_graph_clone_preserves_tt_adapter()
        _patch_shape_value_nodes_for_sh_values()

        options = resolve_profile_options(profile, overrides=kwargs)

        data_graph, shacl_graph, ont_graph = normalize_graph_inputs(
            data_graph,
            shacl_graph,
            ont_graph,
        )

        ensure_graph_mutable(data_graph, name="data_graph")

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
                    "pySHACL version - see docs/pyshacl-upstream-issues.md."
                )

        # SHACL 1.2 Node Expressions moved to the shnex: namespace
        # (https://www.w3.org/TR/shacl12-node-expr/); pySHACL 0.40.0 only
        # knows the old sh:union/sh:intersection/sh:filterShape/sh:path
        # forms. starshacl.node_expressions adds the 21 shnex:
        # operators and (via starshacl.sparql_node_expressions) the
        # sparql: namespace (SPARQL 1.1/1.2 built-in functions/operators as
        # node expressions) without touching pySHACL's own handling of the
        # old forms - see node_expressions.py's own docstring for the full
        # design. Checking for sparql:-namespaced predicates here too
        # (not just shnex:) matters on its own: a shapes graph using ONLY
        # sparql: node expressions, no shnex: ones at all, is entirely
        # legitimate (confirmed via the W3C SHACL 1.2 Node Expressions test
        # suite, which has fixtures doing exactly this) - found live as a
        # real wiring gap, not just a hypothetical, while checking that this
        # session's new sparql: support was reachable through the real
        # validate() entrypoint, not only through eval_expr() called
        # directly (which every test in tests/w3c_suite/ does, so it never
        # exercised this trigger condition at all).
        if shacl_graph is not None and any(
            True
            for p in shacl_graph.predicates()
            if str(p).startswith(str(SHNEX)) or str(p).startswith(str(SPARQL_EXPR_NS))
        ):
            from starshacl.node_expressions import patch_node_expressions_for_shnex

            if not patch_node_expressions_for_shnex():
                raise NotImplementedError(
                    "shnex:/sparql: (SHACL 1.2 Node Expressions) predicates were found in "
                    "the shapes graph, but starShacl's support could not be wired into "
                    "this pySHACL version - see starshacl/node_expressions.py."
                )

        # SHACL 1.2 Core: a shapes graph can cross-reference reusable
        # modules via owl:imports (optionally redirected through
        # owl:versionIRI for versioned modules). This library doesn't
        # dictate a network-fetching policy, so retrieval is delegated to a
        # caller-supplied shapes_graph_loader; when none is given (the
        # default), shacl_graph is used exactly as provided, unchanged.
        if shacl_graph is not None and shapes_graph_loader is not None:
            shacl_graph = _resolve_shapes_graph_imports(shacl_graph, graph_loader=shapes_graph_loader)

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

        # Predicates registered as real pySHACL constraint components (see
        # starshacl/native_components.py) whose value is itself a referenced
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
        # even though starshacl/native_components.py fully supports them -
        # confirmed empirically, not merely suspected. starshacl.meta_shapes
        # fully replaces pySHACL's own mechanism (not supplements it -
        # running both would still reject the 8 widened forms via
        # pySHACL's unmodified check) with an assembled graph: pySHACL's
        # own base with those 8 now-too-strict triples removed, plus
        # starShacl's own SHACL 1.2 validation/presentation rules, plus
        # any caller-supplied meta_shapes_extra graphs.
        if shacl_graph is not None and options.get("meta_shacl"):
            from starshacl.meta_shapes import meta_validate

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
        options.pop("meta_shacl", None)

        # Every SHACL 1.2 predicate pySHACL doesn't natively implement is now
        # registered as a real pySHACL constraint component (see
        # starshacl/native_components.py, register_native_components() -
        # called above via StarShaclValidator.validate()'s own module import)
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
        # see starshacl/native_components.py) needs to consult the shapes
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

        conforms, report_graph, report_text = self.validate_fn(
            data_graph=encoded_data,
            shacl_graph=encoded_shapes,
            ont_graph=encoded_ont,
            **options,
        )

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

        conforms = self._annotate_conformance_disallows(out_report, options, conforms)

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

    def _ensure_native_component_shapes_typed(self, shacl_graph: Any) -> Any:
        """Type the values of shape-expecting native-component predicates
        (see ``starshacl.native_components.SHAPE_EXPECTING_PREDICATES``) as
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
        ``where_shape``, for ``sh:targetWhere``. Runs one batched nested
        ``validate()`` call (candidates as ``sh:targetNode`` on ``where_shape``)
        rather than one call per candidate. Excludes the triggering
        ``(shape_node, sh:targetWhere, where_shape)`` triple from the copy
        used for that nested call, or it would re-trigger this exact check on
        itself forever.
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

        fresh_validator = StarShaclValidator()
        result = fresh_validator.validate(data_graph=data_graph, shacl_graph=augmented, meta_shacl=False)

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

            focus_nodes = self.target_nodes(data_graph=data, shacl_graph=shapes, shape_node=shape)

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
        """
        report_node = next((s for s, _, _ in report_graph.triples((None, RDF.type, SH.ValidationReport))), None)
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

    def _humanize_report_text(self, report_text: str) -> str:
        """Replace encoded triple-term URIs embedded in pySHACL's report text
        with a readable ``<<( s p o )>>`` rendering.

        pySHACL builds this text per-result before starShacl ever sees it, so
        unlike ``report_graph`` (which we decode via ``adapter.decode_graph``)
        there's no structured graph to decode - only string substitution
        against the adapter's own encoding registry. Applied repeatedly so
        nested triple terms (whose components are themselves encoded URIs)
        resolve fully.
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

            focus_nodes = self.target_nodes(data_graph=data, shacl_graph=shapes, shape_node=shape)

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
        data_graph: Any,
        shacl_graph: Any,
        ont_graph: Any | None = None,
        **kwargs: Any,
    ) -> RulesResult:
        options = resolve_profile_options("rules", overrides=kwargs)

        result = self.validate(
            data_graph=data_graph,
            shacl_graph=shacl_graph,
            ont_graph=ont_graph,
            profile="rules",
            **options,
        )

        out_data = result.data_graph or data_graph
        if shacl_graph is not None:
            normalized_shapes = normalize_graph_inputs(shacl_graph, None, None)[0]
            for triple in _global_sparql_rule_triples(out_data, normalized_shapes):
                out_data.add(triple)

        return RulesResult(
            data_graph=out_data,
            report_graph=result.report_graph,
            report_text=result.report_text,
            conforms=result.conforms,
            diagnostics=result.diagnostics,
        )


_filter_shape_patch_status: bool | None = None


def _patch_shape_validate_for_filter_shape() -> bool:
    """Apply a targeted compatibility shim for the confirmed pySHACL bug in
    ``sh:filterShape`` (see ``docs/pyshacl-upstream-issues.md``): patches
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
    """
    global _filter_shape_patch_status
    if _filter_shape_patch_status is not None:
        return _filter_shape_patch_status

    try:
        import pyshacl.shape
        from pyshacl.pytypes import SHACLExecutor

        original_validate = pyshacl.shape.Shape.validate
        if getattr(original_validate, "_starshacl_filter_shape_patch", False):
            _filter_shape_patch_status = True
            return True

        def _patched_validate(self, executor_or_graph, target_graph_or_focus=None, focus=None, **kwargs):
            if isinstance(executor_or_graph, SHACLExecutor):
                return original_validate(self, executor_or_graph, target_graph_or_focus, focus=focus, **kwargs)
            # The broken calling convention: filter_shape.validate(data_graph, node).
            return original_validate(self, SHACLExecutor(), executor_or_graph, focus=target_graph_or_focus)

        _patched_validate._starshacl_filter_shape_patch = True  # type: ignore[attr-defined]
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
    clone's actual triples (the flattened ``urn:starshacl:tt:HASH``
    encoding) are faithfully copied.

    Confirmed live (2026-07-31), found while investigating why
    ``ReifierShapeConstraintComponent`` silently stopped finding any
    reifiers - and reported vacuous conformance - specifically when
    ``advanced=True`` (needed for `sh:expression`/`sh:rule` elsewhere, and
    therefore always passed by ``tests/w3c_suite/test_w3c_validate.py`` since
    it can't tell in advance which fixtures need it): without ``_tt_adapter``,
    ``native_components.py``'s ``_get_tt_adapter()``/``_encode_key()`` fall
    back to treating a ``(focus, path, value)`` tuple as an un-encodable raw
    value, which can never match the graph's actual encoded
    ``rdf:reifies`` triples. The same helper backs ``sh:TripleTerm`` node-kind
    recognition (``_is_encoded_triple_term``), so this affects more than just
    ``sh:reifierShape`` - anything relying on triple-term encoding awareness,
    combined with ``advanced=True``.

    Patches ``pyshacl.graph_abstraction.RdfLibDataGraph.clone`` to copy
    ``_tt_adapter`` from the pre-clone ``.impl`` onto the post-clone
    ``.impl`` when present - a strict superset of the original behavior,
    a no-op for any graph without a ``_tt_adapter`` (i.e. every use of
    pySHACL directly, or of starShacl without triple-term data).

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
        if getattr(original_clone, "_starshacl_tt_adapter_patch", False):
            _rdflib_data_graph_clone_patch_status = True
            return True

        def _patched_clone(self, destination=None, identifier=None):
            cloned = original_clone(self, destination, identifier)
            adapter = getattr(self.impl, "_tt_adapter", None)
            if adapter is not None:
                cloned.impl._tt_adapter = adapter
            return cloned

        _patched_clone._starshacl_tt_adapter_patch = True  # type: ignore[attr-defined]
        ga.RdfLibDataGraph.clone = _patched_clone
        _rdflib_data_graph_clone_patch_status = True
    except Exception:
        _rdflib_data_graph_clone_patch_status = False

    return _rdflib_data_graph_clone_patch_status


def _compute_sh_values(shape: Any, values_node: Any, target_graph: Any, focus_node: Any) -> list:
    """The computed value set for one focus node, per a property shape's
    ``sh:values`` (SHACL 1.2 Core's "new ``sh:values``" mechanism, a
    `sh:PropertyRule`-adjacent but distinct feature): either a full
    ``sh:select`` query (using its own single projected variable, whatever
    it's named) or a single ``sh:sparqlExpr`` scalar expression (wrapped
    into a one-row ``SELECT (<expr> AS ?_computed) WHERE {}``), both
    evaluated with ``$this``/``?this`` bound to ``focus_node`` exactly the
    way ``sh:sparql`` constraints already do. Reuses pySHACL's own
    ``SPARQLQueryHelper`` wholesale (prefix collection via ``sh:prefixes``,
    ``$this`` pre-binding) rather than reimplementing either - the *only*
    new piece is calling it against a value-computation site pySHACL itself
    has no notion of.
    """
    from pyshacl.helper import get_query_helper_cls

    select_vals = list(shape.sg.graph.objects(values_node, SH.select))
    expr_vals = list(shape.sg.graph.objects(values_node, SH.sparqlExpr))
    if select_vals:
        query_text = str(select_vals[0])
    elif expr_vals:
        query_text = f"SELECT ({expr_vals[0]} AS ?_computed) WHERE {{}}"
    else:
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
    special-casing each constraint component individually: a property shape
    carrying ``sh:values`` gets its value set replaced transparently, and
    every *other* constraint on that shape (``sh:datatype``, ``sh:hasValue``
    in both W3C SHACL 1.2 test suite fixtures this was found via,
    ``property-select-001``/``property-sparqlExpr-001``) then runs
    completely unmodified against the computed values. Falls straight
    through to the original method for every shape without ``sh:values``.

    Idempotent and defensive like the other patches in this module -
    returns ``False`` without raising if pySHACL's internals don't match
    what this shim expects.
    """
    global _value_nodes_patch_status
    if _value_nodes_patch_status is not None:
        return _value_nodes_patch_status

    try:
        import pyshacl.shape

        original_value_nodes = pyshacl.shape.Shape.value_nodes
        if getattr(original_value_nodes, "_starshacl_values_patch", False):
            _value_nodes_patch_status = True
            return True

        def _patched_value_nodes(self, target_graph, focus, sparql_mode=False, debug=False):
            values_node = next(iter(self.sg.graph.objects(self.node, SH.values)), None)
            if values_node is not None and self.is_property_shape:
                focus_list = focus if isinstance(focus, (tuple, list, set)) else [focus]
                return {f: set(_compute_sh_values(self, values_node, target_graph, f)) for f in focus_list}
            return original_value_nodes(self, target_graph, focus, sparql_mode=sparql_mode, debug=debug)

        _patched_value_nodes._starshacl_values_patch = True  # type: ignore[attr-defined]
        pyshacl.shape.Shape.value_nodes = _patched_value_nodes
        _value_nodes_patch_status = True
    except Exception:
        _value_nodes_patch_status = False

    return _value_nodes_patch_status


def _default_validate(**kwargs: Any) -> tuple[bool, Graph, str]:
    from pyshacl import validate

    return validate(**kwargs)


def _is_starlayer_graph(value: Any) -> bool:
    try:
        from starlayergraph.graph.starlayer_graph import StarLayerGraph
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
    component - see ``starshacl/native_components.py``) sees them without
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
    the SHACL 1.2 Core spec: iteratively follow the property path
    ``^owl:versionIRI?/owl:imports`` - i.e. when the graph retrieved for an
    imported IRI declares that same IRI as *its own* ``owl:versionIRI``, the
    IRI of the ``owl:versionIRI`` triple's subject is used as the canonical
    shapes-graph IRI both for deduplication and for following *that* graph's
    own ``owl:imports`` statements, so versioned modules resolve correctly.

    Retrieval itself is delegated to ``graph_loader`` (given an import IRI,
    returns a parsed graph, or ``None`` if it can't be resolved) - this
    library doesn't dictate a network-fetching policy; an unresolvable
    import is simply skipped rather than raising.
    """
    merged = type(shacl_graph)()
    for triple in shacl_graph:
        merged.add(triple)

    fetched: set[Any] = set()
    imported_canonical: set[Any] = set()
    pending = list(dict.fromkeys(o for _, _, o in shacl_graph.triples((None, OWL.imports, None))))

    while pending:
        target_iri = pending.pop(0)
        if target_iri in fetched:
            continue
        fetched.add(target_iri)

        imported_graph = graph_loader(target_iri)
        if imported_graph is None:
            continue

        canonical_id = next(
            (s for s, _, o in imported_graph.triples((None, OWL.versionIRI, None)) if o == target_iri),
            target_iri,
        )
        if canonical_id in imported_canonical:
            continue
        imported_canonical.add(canonical_id)
        fetched.add(canonical_id)

        for triple in imported_graph:
            merged.add(triple)

        for _, _, next_iri in imported_graph.triples((canonical_id, OWL.imports, None)):
            if next_iri not in fetched:
                pending.append(next_iri)

    return merged


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

    This ambiguity is real, not hypothetical: found via
    ``_nodes_conforming_to``'s own nested ``validate()`` call, whose
    ``data_graph`` can itself already contain report-shaped content (e.g.
    the W3C SHACL 1.2 test suite's own manifest format - a fixture using
    ``sht:dataGraph <>`` treats its own ``mf:result [ a sh:ValidationReport ;
    sh:conforms ... ; sh:result [...] ]`` expected-result block as ordinary
    data). If some *other*, genuine violation's value/focus node happens to
    equal that embedded block, pySHACL's own report-graph construction
    copies its triples into the output report as part of representing that
    value - producing a second, spurious ``sh:ValidationReport``-typed node
    that a naive "first/any node of this type" scan can't tell apart from
    the real one. The real one is identifiable structurally: it is always a
    fresh ``BNode()`` that nothing else in the graph points to, whereas an
    incidental one was pulled in specifically *because* something else
    references it.
    """
    nodes = list(report_graph.triples((None, RDF.type, SH.ValidationReport)))
    candidates = [s for s, _, _ in nodes]
    if len(candidates) <= 1:
        return candidates[0] if candidates else None
    roots = [n for n in candidates if next(report_graph.subjects(None, n), None) is None]
    if len(roots) == 1:
        return roots[0]
    return candidates[0]


def _global_sparql_rules(shacl_graph: Any) -> list:
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
    """
    referenced = set(shacl_graph.objects(None, SH.rule))
    return [r for r in shacl_graph.subjects(RDF.type, SH.SPARQLRule) if r not in referenced]


def _global_sparql_rule_triples(data_graph: Any, shacl_graph: Any) -> list[tuple]:
    """Every triple produced by running each global ``sh:SPARQLRule``'s own
    ``sh:construct`` query once against ``data_graph`` (no per-focus-node
    iteration, no ``$this`` binding - the query's own graph pattern is
    matched directly against the whole graph, exactly like an ordinary
    standalone SPARQL CONSTRUCT). Honors ``sh:deactivated`` on the rule node
    itself. Prefix resolution reuses ``_ambient_shapes_graph_prefixes`` (see
    that function's own docstring) since a global rule, having no shape of
    its own, can't carry an explicit ``sh:prefixes`` reference at all -
    confirmed via the fixture this was found through, whose ``ex:`` prefix
    is declared only via an ambient ``sh:ShapesGraph`` node.
    """
    added: list[tuple] = []
    ambient_prefixes = _ambient_shapes_graph_prefixes(shacl_graph)
    prefix_text = "".join(f"PREFIX {p}: <{ns}>\n" for p, ns in ambient_prefixes.items())
    for rule_node in _global_sparql_rules(shacl_graph):
        deactivated = next(iter(shacl_graph.objects(rule_node, SH.deactivated)), None)
        if deactivated is not None and bool(deactivated.value if hasattr(deactivated, "value") else deactivated):
            continue
        construct_vals = list(shacl_graph.objects(rule_node, SH.construct))
        if not construct_vals:
            continue
        query_text = prefix_text + str(construct_vals[0])
        try:
            for triple in data_graph.query(query_text):
                added.append(triple)
        except Exception:
            continue
    return added


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
