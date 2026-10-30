"""``validate()``: data graph + shapes graph -> ``Outcome``."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from rdflib import URIRef

from starlayer.shacl_engine import components  # noqa: F401  (registers the constraint components)
from starlayer.shacl_engine.executor import Result, run
from starlayer.shacl_engine.plan import Plan
from starlayer.shacl_engine.report import annotate_provenance, build_report, conforms

DEFAULT_MAX_VALIDATION_DEPTH = 500  # the old validator's default (starlayer.shacl.recursion.MAX_VALIDATION_DEPTH)


@dataclass
class Outcome:
    conforms: bool
    report_graph: Any
    results: list[Result]
    rule_result: Any = None
    data_graph: Any = None  # the caller's data graph with the inferred triples added, when ``inplace=True``


def _identity_of(graph: Any) -> Any:
    """A graph's own IRI (``graph.identifier``) when it has a real one; the anonymous blank node every rdflib graph
    gets carries no identity worth reporting."""
    ident = getattr(graph, "identifier", None)
    return ident if isinstance(ident, URIRef) else None


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

    Not offered: the old validator's ``decode_report`` (it undoes the triple-term encoding it applies for pySHACL; this
    engine handles triple terms natively and never encodes, so there is nothing to decode) and ``iterate_rules``.
    """
    from starlayer.shacl_engine.entailment import resolve_data_view

    shapes = shapes_graph
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
    shapes = shapes if shapes is not None else data_graph
    data_graph = resolve_data_view(data_graph, shapes, inference=inference, ont_graph=ont_graph)
    rule_result = None
    if rules is not False:
        from starlayer.shacl_engine.rules import apply_rules, entailment_selection

        active, sets = entailment_selection(shapes) if rules is None else (True, None)
        if active:
            rule_result = apply_rules(data_graph, shapes, rule_sets=sets or None)
            data_graph = rule_result.view
    results = run(Plan(shapes_graph=shapes), data_graph, abort_on_first=abort_on_first, max_validation_depth=max_validation_depth)
    report = build_report(results, shapes, data_graph, conformance_disallows)
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
            if triple not in original_data:
                original_data.add(triple)
    return Outcome(
        conforms=conforms(results, conformance_disallows),
        report_graph=report,
        results=results,
        rule_result=rule_result,
        data_graph=original_data if inplace else None,
    )
