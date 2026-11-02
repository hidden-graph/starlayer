"""``validate()``: data graph + shapes graph -> ``Outcome``."""

from __future__ import annotations

import warnings
from collections.abc import Iterable
from dataclasses import dataclass, field
from typing import Any

from rdflib import URIRef

from starlayer.shacl_engine import components  # noqa: F401  (registers the constraint components)
from starlayer.shacl_engine.executor import Result, run
from starlayer.shacl_engine.fidelity import check_lexical_fidelity
from starlayer.shacl_engine.plan import Path, Plan
from starlayer.shacl_engine.report import annotate_provenance, build_report, conforms
from starlayer.shacl_engine.terms import (
    LegacyTermView,
    StarLayerFidelityWarning,
    check_graphs,
    engine_view,
    from_engine,
    from_engine_triple,
    to_engine,
    with_term_policy,
)
from starlayer.shacl_engine.text import result_messages

DEFAULT_MAX_VALIDATION_DEPTH = 500  # the old validator's default (starlayer.shacl.recursion.MAX_VALIDATION_DEPTH)


@dataclass
class Outcome:
    conforms: bool
    report_graph: Any
    results: list[Result]
    rule_result: Any = None
    data_graph: Any = None  # the caller's data graph with the inferred triples added, when ``inplace=True``
    invalid_terms: tuple = ()  # ill-formed terms processed as opaque stand-ins (``invalid_terms="lenient"``); else empty
    recursion_revisits: int = 0  # recursive (shape, node) re-entries during the run (diagnostics)
    warnings: tuple[str, ...] = ()  # diagnostics of this run, e.g. the lexical-fidelity warning (``fidelity.py``)
    _text_inputs: Any = field(default=None, repr=False, compare=False)  # (shapes, data view, data_graph_iri) for report_text
    _report_text: str | None = field(default=None, repr=False, compare=False)

    @property
    def report_text(self) -> str:
        """The human-readable report (the old ``ValidationResult.report_text`` layout; see ``text.py``), built on first use."""
        if self._report_text is None:
            from starlayer.shacl_engine.text import report_text

            shapes, data, data_iri = self._text_inputs if self._text_inputs is not None else (None, None, None)
            self._report_text = report_text(self.results, self.conforms, shapes, data, self.report_graph, data_iri)
        return self._report_text

    @property
    def diagnostics(self) -> Any:
        """``ExecutionDiagnostics`` for this run. The engine never encodes triple terms, so the encode/decode counters are 0;
        ``report_triples`` is the size of the report graph. ``recursion_revisits`` counts recursive re-entries."""
        from starlayer.shacl.results import ExecutionDiagnostics

        return ExecutionDiagnostics(report_triples=len(self.report_graph), recursion_revisits=self.recursion_revisits, inplace_data_triples=len(self.data_graph) if self.data_graph is not None else 0)


def legacy_path(p: Path | None) -> Path | None:
    """A ``Path`` with rdflib terms (the public ``Outcome.results`` speak the caller's term model)."""
    if p is None:
        return None
    return Path(kind=p.kind, iri=from_engine(p.iri), args=tuple(legacy_path(a) for a in p.args), node=from_engine(p.node))


def legacy_result(r: Result) -> Result:
    """A ``Result`` with rdflib / StarLayer terms: the term-model boundary of ``Outcome.results``."""
    return Result(
        focus=from_engine(r.focus),
        path=legacy_path(r.path),
        value=from_engine(r.value),
        has_value=r.has_value,
        component=from_engine(r.component),
        shape=from_engine(r.shape),
        severity=from_engine(r.severity),
        messages=tuple(from_engine(m) for m in r.messages),
        source_constraint=from_engine(r.source_constraint),
        annotations=tuple((from_engine(p), from_engine(v)) for p, v in r.annotations),
        details=tuple(legacy_result(d) for d in r.details),
    )


def _identity_of(graph: Any) -> Any:
    """A graph's own IRI (``graph.identifier``) when it has a real one; the anonymous blank node every rdflib graph
    gets carries no identity worth reporting."""
    ident = getattr(graph, "identifier", None)
    return ident if isinstance(ident, URIRef) else None


@with_term_policy
def validate(
    data_graph: Any,
    shapes_graph: Any = None,
    *,
    conformance_disallows: Any = None,
    rules: bool | None = None,
    inference: Any = None,
    ont_graph: Any = None,
    data_graph_iri: Any = None,
    shapes_graph_iri: Any = None,
    shapes_graph_resource: Any = None,
    specification_graph: Any = None,
    include_used_configuration: bool = False,
    abort_on_first: bool = False,
    max_validation_depth: int | None = DEFAULT_MAX_VALIDATION_DEPTH,
    inplace: bool = False,
    meta_shacl: Any = None,
    shapes_graph_loader: Any = None,
    ignore_imports: bool = False,
    meta_shapes_extra: Any = (),
    plan: Plan | None = None,
    plan_cache: dict | None = None,
) -> Outcome:
    """Validate ``data_graph`` against ``shapes_graph`` (default: the data graph itself).

    ``rules``: ``None`` runs the inference rules first when the shapes graph declares ``sh:entailment``; ``True`` runs the
    default rule set; ``False`` never. Rules never modify ``data_graph``; validation then runs on data plus inferred
    triples, and the ``RuleResult`` is on ``Outcome.rule_result``.

    ``inference`` (an entailment regime such as ``"rdfs"`` or ``"owlrl"``) and ``sh:entailment`` declared in the shapes
    graph run the entailment closure first (see ``entailment.py``); ``ont_graph`` supplies axioms visible to entailment
    only. Neither modifies ``data_graph`` unless ``inplace=True``, which then adds the inferred and entailed triples to it
    (returned as ``Outcome.data_graph``).

    Report provenance: ``data_graph_iri`` / ``shapes_graph_iri`` become ``sh:usedDataGraph`` / ``sh:usedShapesGraph``
    (each falls back to the graph's own ``identifier`` when that is an IRI). ``shapes_graph_resource`` names a
    ``sh:ShapesGraph`` module of ``shapes_graph`` to validate against (its IRI is then the ``sh:usedShapesGraph``), or any
    other IRI, used only as the provenance tag; it needs an explicit ``shapes_graph``. ``include_used_configuration``
    adds a ``sh:ProcessorConfiguration`` recording the options of this run; ``specification_graph`` lets the Profiling
    ``dcterms:conformsTo`` rule fire as well. When both graph identities are known the ``sh:conformsTo`` rule runs.

    ``abort_on_first``: stop at the first constraint component that produces a result. ``max_validation_depth``: bound on
    shape nesting; exceeding it raises ``ShapeError`` (the old validator raises too; its default is 500). ``None``
    removes the bound. Recursive shapes: see ``Context.conforms``.

    ``meta_shacl``, ``shapes_graph_loader``, ``ignore_imports`` and ``meta_shapes_extra`` are the seam for
    ``shacl_engine.meta`` and ``shacl_engine.imports`` (see the TODO below).

    ``plan``: a ``Plan`` already built over ``shapes_graph`` (used by ``validate_each`` to parse the shapes once); it
    must belong to the shapes graph actually validated against.

    ``plan_cache``: a dict a caller keeps across calls (the adapter's ``validate_each``); the Plan built over an explicit
    ``shapes_graph`` is stored under ``(id(shapes_graph), shapes_graph_resource)`` and reused by later calls with the same
    shapes graph object (the caller must keep that object alive and unchanged).

    ``invalid_terms``: what to do with terms that are not RDF terms (a relative IRI, a blank node id or language tag
    Oxigraph rejects): ``"error"`` (default) raises ``terms.TermError`` before validating; ``"lenient"`` processes them as
    opaque terms and lists them on ``Outcome.invalid_terms``. See ``terms.TermError`` for the policy and its reasoning.

    Not offered: the old validator's ``decode_report`` (it undoes the triple-term encoding it applies for pySHACL; this
    engine handles triple terms natively and never encodes, so there is nothing to decode) and ``iterate_rules``.
    """
    from starlayer.shacl_engine.entailment import resolve_data_view

    # One up-front check of the caller's graphs for terms that are not RDF terms (``terms.TermError``): raises, or under
    # ``invalid_terms="lenient"`` lists them on ``Outcome.invalid_terms``.
    invalid = check_graphs((data_graph, "data graph"), (shapes_graph, "shapes graph"), (ont_graph, "ontology graph"))
    shapes = shapes_graph
    cache_key = (id(shapes_graph), shapes_graph_resource) if plan_cache is not None and shapes_graph is not None else None
    if plan is None and cache_key is not None:
        plan = plan_cache.get(cache_key)
    # TODO(wiring): the seam for ``imports.resolve_imports`` and ``meta.meta_validate`` (separate modules). Lazy and
    # guarded by ImportError. Imports are resolved only when a loader is given: calling it with none would make the
    # default raise on any unresolved owl:imports, which the lead decides when wiring the old validator's default
    # (``ignore_imports=False`` raises there). ``meta_shacl`` truthy runs the SHACL-SHACL preflight on the shapes graph.
    if shapes is not None and shapes_graph_loader is not None:
        try:
            from starlayer.shacl_engine.imports import resolve_imports
        except ImportError:
            pass
        else:
            shapes = resolve_imports(shapes, shapes_graph_loader=shapes_graph_loader, ignore_imports=ignore_imports)
    if meta_shacl:
        try:
            from starlayer.shacl_engine.meta import meta_validate
        except ImportError:
            pass
        else:
            meta_validate(
                shapes if shapes is not None else data_graph, meta_shacl=meta_shacl, meta_shapes_extra=meta_shapes_extra
            ).raise_if_invalid()

    if data_graph_iri is None:
        data_graph_iri = _identity_of(data_graph)
    if shapes_graph_resource is not None:
        from starlayer.shacl_engine.modules import resolve_shapes_resource

        shapes, resolved = resolve_shapes_resource(shapes, shapes_graph_resource)
        if shapes_graph_iri is None:
            shapes_graph_iri = resolved
    elif shapes_graph_iri is None and shapes is not None:
        shapes_graph_iri = _identity_of(shapes)
    original_data = data_graph
    shapes = engine_view(shapes if shapes is not None else data_graph, "shapes graph")  # the term-model boundary: engine terms inside
    conformance_disallows = to_engine(conformance_disallows)
    data_graph = resolve_data_view(data_graph, shapes, inference=inference, ont_graph=ont_graph)
    rule_result = None
    if rules is not False:
        from starlayer.shacl_engine.rules import apply_rules, entailment_selection

        active, sets = entailment_selection(shapes) if rules is None else (True, None)
        if active:
            rule_result = apply_rules(data_graph, shapes, rule_sets=sets or None)
            data_graph = rule_result.view
    stats: dict = {}
    if plan is None:
        plan = Plan(shapes_graph=shapes)
        if cache_key is not None:
            plan_cache[cache_key] = plan
    results = run(
        plan,
        data_graph,
        abort_on_first=abort_on_first,
        max_validation_depth=max_validation_depth,
        stats=stats,
    )
    run_warnings: list[str] = []
    fidelity = check_lexical_fidelity(plan, data_graph)
    if fidelity is not None:
        run_warnings.append(fidelity)
        warnings.warn(fidelity, StarLayerFidelityWarning, stacklevel=3)
    shapes_view, data_view = LegacyTermView(shapes), LegacyTermView(data_graph)
    report = build_report(
        results, shapes, data_graph, conformance_disallows, messages_for=lambda r: result_messages(legacy_result(r), shapes_view, data_view)
    )
    annotate_provenance(
        report,
        data_graph_iri=data_graph_iri,
        shapes_graph_iri=shapes_graph_iri,
        include_used_configuration=include_used_configuration,
        configuration={
            "abortOnFirst": abort_on_first,
            "maxValidationDepth": max_validation_depth,
            "rules": rules,
            "inference": inference if isinstance(inference, str) else None,
            "inplace": inplace,
        },
        specification_graph=specification_graph,
    )
    if inplace and data_graph is not original_data:
        for triple in list(data_graph.triples((None, None, None))):
            triple = from_engine_triple(triple)
            if triple not in original_data:
                original_data.add(triple)
    return Outcome(
        conforms=conforms(results, conformance_disallows),
        report_graph=report,
        results=[legacy_result(r) for r in results],
        rule_result=rule_result,
        invalid_terms=invalid,
        warnings=tuple(run_warnings),
        data_graph=original_data if inplace else None,
        recursion_revisits=stats.get("recursion_revisits", 0),
        _text_inputs=(shapes_view, data_view, data_graph_iri),
    )


@with_term_policy
def validate_each(
    data_graphs: Iterable[Any],
    shapes_graph: Any = None,
    ont_graph: Any = None,
    **kwargs: Any,
) -> dict[int, Outcome]:
    """Validate each of ``data_graphs`` independently against the same shapes graph; returns ``{index: Outcome}``.

    ``kwargs`` are those of :func:`validate`. With an explicit ``shapes_graph`` the imports, the meta-SHACL preflight, the
    ``shapes_graph_resource`` selection and the shape parsing happen once and are shared by every graph. Without one, each
    data graph doubles as its own shapes graph, as in :func:`validate`.
    """
    graphs = list(data_graphs)
    if shapes_graph is None or not graphs:
        return {i: validate(g, None, ont_graph=ont_graph, **kwargs) for i, g in enumerate(graphs)}
    shapes = shapes_graph
    shapes_iri = kwargs.pop("shapes_graph_iri", None)
    loader, ignore_imports = kwargs.pop("shapes_graph_loader", None), kwargs.pop("ignore_imports", False)
    meta_shacl, extra = kwargs.pop("meta_shacl", None), kwargs.pop("meta_shapes_extra", ())
    resource = kwargs.pop("shapes_graph_resource", None)
    if loader is not None:
        from starlayer.shacl_engine.imports import resolve_imports

        shapes = resolve_imports(shapes, shapes_graph_loader=loader, ignore_imports=ignore_imports)
    if meta_shacl:
        from starlayer.shacl_engine.meta import meta_validate

        meta_validate(shapes, meta_shacl=meta_shacl, meta_shapes_extra=extra).raise_if_invalid()
    if resource is not None:
        from starlayer.shacl_engine.modules import resolve_shapes_resource

        shapes, resolved = resolve_shapes_resource(shapes, resource)
        shapes_iri = shapes_iri if shapes_iri is not None else resolved
    elif shapes_iri is None:
        shapes_iri = _identity_of(shapes)
    shared = Plan(shapes_graph=engine_view(shapes, "shapes graph"))
    return {
        i: validate(g, shapes, ont_graph=ont_graph, shapes_graph_iri=shapes_iri, plan=shared, **kwargs)
        for i, g in enumerate(graphs)
    }
