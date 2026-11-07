"""The public SHACL entry points (``validate``, ``apply_rules``, ``evaluate``, ``extract_subgraph``, ...) on the native engine
(``starlayer.shacl_engine``): graph normalisation, option translation and result shaping.

An option the engine has no use for is a ``TypeError`` (an unknown keyword), as is a misspelt one. The engine follows the SHACL 1.2
drafts where the earlier validator differed; see ``docs/working/shacl-engine-differential.md``.
"""

from __future__ import annotations

import contextlib
import contextvars
from collections.abc import Iterator
from typing import Any

import pyoxigraph as ox

from starlayer.shacl_engine.terms import RDF, SH, term_policy, to_engine

_RDF_REIFIES = RDF.reifies

# The keywords ``validate()`` (and so ``apply_rules()``) take besides its named parameters: the option presets of
# ``validation_modes`` and their per-call overrides. ``advanced=False`` turns rule execution off; ``debug`` is accepted and ignored;
# ``invalid_terms`` is ``"error"`` (the default: a graph holding a term that is not an RDF term, such as a relative IRI, raises
# ``TermError``) or ``"lenient"`` (such terms are processed as opaque stand-ins).
VALIDATE_OPTIONS = frozenset(
    {
        "advanced",
        "debug",
        "inplace",
        "meta_shacl",
        "allow_warnings",
        "allow_infos",
        "abort_on_first",
        "abort_on_error",
        "max_validation_depth",
        "inference",
        "invalid_terms",
    }
)

_PLAN_CACHE: contextvars.ContextVar[dict | None] = contextvars.ContextVar("starlayer_shacl_plan_cache", default=None)


@contextlib.contextmanager
def shared_plans() -> Iterator[dict]:
    """While active, validations over the same explicit shapes graph object share one parsed ``Plan`` (used by the
    ``validate_each`` entry points: the shapes are parsed once for the whole batch, not once per data graph)."""
    cache: dict = {}
    token = _PLAN_CACHE.set(cache)
    try:
        yield cache
    finally:
        _PLAN_CACHE.reset(token)


# ---------------------------------------------------------------------------------------------------------------------
# option translation


def conformance_disallows_for(allow_warnings: Any, allow_infos: Any) -> Any:
    """The engine's ``conformance_disallows`` (the lowest severity that blocks conformance) for ``allow_warnings`` /
    ``allow_infos``: allowing warnings also allows infos (only violations block); allowing infos alone lets Info through
    (Warning and Violation block); neither: ``None`` (Info and above block, the draft's default)."""
    if allow_warnings:
        return SH.Violation
    if allow_infos:
        return SH.Warning
    return None


def translate_validate_options(options: dict[str, Any]) -> dict[str, Any]:
    """Map the resolved option dict (mode preset plus overrides) to ``shacl_engine.validate`` keywords. ``advanced`` False means
    no rule execution (``rules=False``); the ``"rules"`` preset (``iterate_rules``) means ``rules=True``; otherwise ``rules=None``,
    which runs rules only when the shapes graph declares ``sh:entailment`` (the draft)."""
    out: dict[str, Any] = {}
    out["conformance_disallows"] = conformance_disallows_for(options.get("allow_warnings"), options.get("allow_infos"))
    out["inplace"] = bool(options.get("inplace"))
    out["abort_on_first"] = bool(options.get("abort_on_first") or options.get("abort_on_error"))
    if "max_validation_depth" in options:  # ``None`` is meaningful: it removes the bound
        out["max_validation_depth"] = options["max_validation_depth"]
    meta = options.get("meta_shacl")
    if meta:
        out["meta_shacl"] = meta
    if options.get("invalid_terms") is not None:
        out["invalid_terms"] = options["invalid_terms"]
    if options.get("advanced") is False:
        out["rules"] = False
    elif options.get("iterate_rules"):
        out["rules"] = True
    else:
        out["rules"] = None
    return out


def reject_unknown_options(kwargs: dict[str, Any]) -> None:
    """``TypeError`` for an option nobody knows (a typo, or a keyword of the validator this one replaced)."""
    unknown = sorted(set(kwargs) - VALIDATE_OPTIONS)
    if unknown:
        raise TypeError(
            f"unknown option(s) {', '.join(unknown)}; the options are {', '.join(sorted(VALIDATE_OPTIONS))} "
            "(inference is an entailment regime IRI, ENTAILMENT.RDFS for example)"
        )


def _check_imports(shapes: Any, loader: Any, ignore_imports: bool) -> None:
    """``owl:imports`` that are not locally satisfied, with no loader and without ``ignore_imports``, is an error (the engine
    resolves imports only when a loader is given)."""
    if shapes is not None and loader is None and not ignore_imports:
        from starlayer.shacl_engine.imports import resolve_imports

        resolve_imports(shapes, None, False)


def _normalise(data: Any, shapes: Any, ont: Any, invalid_terms: Any = None) -> tuple[Any, Any, Any]:
    """The three graphs as Oxigraph-backed graphs (an rdflib / StarLayerGraph input is copied by the ``from_rdflib`` bridge, under
    the ``invalid_terms`` policy)."""
    import contextlib

    from starlayer.shacl.normalization import normalize_graph_inputs

    with term_policy(invalid_terms) if invalid_terms else contextlib.nullcontext():
        return normalize_graph_inputs(data, shapes, ont)


def _meta_preflight(shapes: Any, meta_shapes_extra: Any, floor: Any) -> None:
    """The ``meta_shacl=True`` preflight on the shapes graph: the caller's ``allow_warnings`` / ``allow_infos`` relax it too (the
    engine's own default tolerates Warning and Info), and the SPARQL text check follows it."""
    from starlayer.shacl.meta_shapes import check_sparql_query_text
    from starlayer.shacl_engine.meta import meta_validate

    meta_validate(
        shapes,
        meta_shacl=True,
        meta_shapes_extra=meta_shapes_extra,
        allow_warnings=floor == SH.Violation,
        allow_infos=floor == SH.Warning,
    )
    check_sparql_query_text(shapes)


def _annotate_conformance_disallows(report: Any, floor: Any) -> None:
    """``sh:conformanceDisallows`` as the report states it: always the explicit set of blocking severities (Violation; Warning
    unless warnings are allowed; Info unless warnings or infos are allowed), where the engine writes the property only for a
    non-default floor."""
    node = next(iter(report.subjects(RDF.type, SH.ValidationReport)), None)
    if node is None:
        return
    disallowed = [SH.Violation]
    if floor in (None, SH.Warning, SH.Info):
        disallowed.append(SH.Warning)
    if floor in (None, SH.Info):
        disallowed.append(SH.Info)
    report.remove((node, SH.conformanceDisallows, None))
    for severity in disallowed:
        report.add((node, SH.conformanceDisallows, severity))


# ---------------------------------------------------------------------------------------------------------------------
# validate


def validate(
    *,
    data_graph: Any,
    shacl_graph: Any,
    ont_graph: Any,
    inference: Any = None,
    mode: Any = None,
    options: dict[str, Any],
    shapes_graph_loader: Any = None,
    ignore_imports: bool = False,
    meta_shapes_extra: Any = (),
    data_graph_iri: Any = None,
    shapes_graph_iri: Any = None,
    shapes_graph_resource: Any = None,
    specification_graph: Any = None,
    include_used_configuration: bool = False,
) -> Any:
    """``validate()`` on the engine: a ``ValidationResult``. ``options`` is the caller's ``**kwargs`` (option overrides);
    ``inference`` is the keyword of ``validate()``, or the schema's bound regime."""
    from starlayer.shacl.results import ValidationResult
    from starlayer.shacl.validation_modes import resolve_mode_options
    from starlayer.shacl_engine import api

    reject_unknown_options(options)
    resolved = resolve_mode_options(mode, overrides=options)
    inference = resolved.get("inference", inference) if "inference" in options else inference
    engine_kwargs = translate_validate_options(resolved)

    original = data_graph
    data, shapes, ont = _normalise(data_graph, shacl_graph, ont_graph, options.get("invalid_terms"))
    cache = _PLAN_CACHE.get()
    if cache is not None and shacl_graph is not None:
        # keep the caller's shapes object alive next to its normalised form, so the (id-keyed) Plan cache stays valid and
        # every item of the batch sees the same shapes object
        shapes = cache.setdefault(("shapes", id(shacl_graph)), (shacl_graph, shapes))[1]
    if shapes_graph_resource is not None and shapes is None:
        raise ValueError(
            "shapes_graph_resource= needs a bound shapes graph to check against - "
            "construct with StarShaclSchema(shacl_graph=...). (If you only "
            "want to record where the shapes came from, pass shapes_graph_iri=.)"
        )
    _check_imports(shapes if shapes is not None else data, shapes_graph_loader, ignore_imports)
    meta_shacl = engine_kwargs.pop("meta_shacl", None)
    if meta_shacl:
        _meta_preflight(
            shapes if shapes is not None else data, meta_shapes_extra, engine_kwargs.get("conformance_disallows")
        )
    outcome = api.validate(
        data,
        shapes,
        inference=inference,
        ont_graph=ont,
        data_graph_iri=data_graph_iri,
        shapes_graph_iri=shapes_graph_iri,
        shapes_graph_resource=shapes_graph_resource,
        specification_graph=specification_graph,
        include_used_configuration=include_used_configuration,
        shapes_graph_loader=shapes_graph_loader,
        ignore_imports=ignore_imports,
        meta_shapes_extra=meta_shapes_extra,
        plan_cache=cache,
        **engine_kwargs,
    )
    _annotate_conformance_disallows(outcome.report_graph, engine_kwargs.get("conformance_disallows"))
    out_data = None
    if engine_kwargs.get("inplace"):
        out_data = original
        if data is not original:  # a graph was converted (or a Store wrapped): write the inferred triples back
            api._write_back(data, original)
    return ValidationResult(
        conforms=outcome.conforms,
        report_graph=outcome.report_graph,
        report_text=outcome.report_text,
        data_graph=out_data,
        diagnostics=outcome.diagnostics,
    )


# ---------------------------------------------------------------------------------------------------------------------
# apply_rules


def _rule_set_iris(rule_set: Any) -> list[Any] | None:
    if rule_set is None:
        return None
    if isinstance(rule_set, (str, ox.NamedNode)) or not hasattr(rule_set, "__iter__"):
        members = [rule_set]
    else:
        members = list(rule_set)
    return [ox.NamedNode(m) if type(m) is str else to_engine(m) for m in members]  # a plain string is an IRI


# validate()'s own keywords, which ``apply_rules()`` forwards to its final validation pass
_VALIDATE_KEYWORDS = (
    "data_graph_iri",
    "shapes_graph_iri",
    "shapes_graph_resource",
    "specification_graph",
    "include_used_configuration",
    "ignore_imports",
    "shapes_graph_loader",
    "meta_shapes_extra",
)


def apply_rules(
    *,
    data_graph: Any,
    shacl_graph: Any,
    ont_graph: Any,
    include_source_rule_provenance: bool,
    rule_set: Any,
    options: dict[str, Any],
) -> Any:
    """``apply_rules()`` on the engine: a ``RulesResult``."""
    from starlayer.shacl.results import RulesResult, ValidationResult
    from starlayer.shacl.validation_modes import resolve_mode_options
    from starlayer.shacl_engine import api, rules
    from starlayer.shacl_engine.entailment import resolve_data_view

    options = dict(options)
    passthrough = {name: options.pop(name) for name in _VALIDATE_KEYWORDS if name in options}
    rule_limits = {name: options.pop(name) for name in ("max_iterations", "max_triples") if name in options}
    reject_unknown_options(options)
    engine_kwargs = translate_validate_options(resolve_mode_options("validation", overrides=options))
    engine_kwargs.pop("inplace", None)
    engine_kwargs["rules"] = False  # the rules have run: the final pass validates the evaluation graph only
    inference = options.get("inference")
    data, shapes, ont = _normalise(
        data_graph, shacl_graph if shacl_graph is not None else data_graph, ont_graph, options.get("invalid_terms")
    )
    meta_shacl = engine_kwargs.pop("meta_shacl", None)
    if meta_shacl:  # the same preflight as validate(), on the shapes graph as given
        _meta_preflight(
            shapes, passthrough.get("meta_shapes_extra", ()), engine_kwargs.get("conformance_disallows")
        )
    if passthrough.get("data_graph_iri") is None:  # the report names the caller's data graph, not the rule overlay view
        passthrough["data_graph_iri"] = api._identity_of(data)
    loader = passthrough.get("shapes_graph_loader")
    if loader is not None:  # the rules of an imported module run too: imports first, as validate() does
        from starlayer.shacl_engine.imports import resolve_imports

        if passthrough.get("shapes_graph_iri") is None:
            passthrough["shapes_graph_iri"] = api._identity_of(shapes)
        shapes = resolve_imports(shapes, loader, bool(passthrough.get("ignore_imports")))
    # "before rules" entailment pass: the rules see the entailed graph (kept as an overlay; entailed triples are not inferred)
    base = resolve_data_view(data, shapes, inference=inference, ont_graph=ont)
    result = rules.apply_rules(
        base, shapes, rule_sets=_rule_set_iris(rule_set), source_rules=bool(include_source_rule_provenance), **rule_limits
    )
    _check_imports(shapes, passthrough.get("shapes_graph_loader"), bool(passthrough.get("ignore_imports")))
    outcome = api.validate(
        result.view,
        shapes,
        inference=inference,
        ont_graph=ont,
        **{"meta_shapes_extra": (), **passthrough},
        **engine_kwargs,
    )
    _annotate_conformance_disallows(outcome.report_graph, engine_kwargs.get("conformance_disallows"))
    validation = ValidationResult(
        conforms=outcome.conforms,
        report_graph=outcome.report_graph,
        report_text=outcome.report_text,
        data_graph=None,
        diagnostics=outcome.diagnostics,
    )
    from starlayer.shacl_engine.graphs import new_graph

    inferred = new_graph(data)
    inferred.extend(list(result.inferred))
    for triple, rule_node in result.source_rules:  # SHACL 1.2 Inference Rules 9: _:r rdf:reifies <<( s p o )>> ; sh:sourceRule <rule>
        reifier = ox.BlankNode()
        inferred.add((reifier, _RDF_REIFIES, ox.Triple(*triple)))
        inferred.add((reifier, SH.sourceRule, rule_node))
    return RulesResult(inferred_graph=inferred, validation=validation)


# ---------------------------------------------------------------------------------------------------------------------
# evaluate / extract_subgraph / target_nodes / shapes-graph helpers


def evaluate(
    data_graph: Any,
    shacl_graph: Any,
    ont_graph: Any,
    *,
    inference: Any,
    focus_nodes: Any,
    properties: Any,
    rules_entailment: bool,
) -> Any:
    """``evaluate()`` on the engine (a plain graph)."""
    from starlayer.shacl_engine.evaluate import evaluate as engine_evaluate

    data, shapes, ont = _normalise(data_graph, shacl_graph if shacl_graph is not None else data_graph, ont_graph)
    return engine_evaluate(
        data,
        shapes,
        ont,
        inference=inference,
        focus_nodes=focus_nodes,
        properties=properties,
        rules_entailment=rules_entailment,
    )


def extract_subgraph(
    data_graph: Any,
    shacl_graph: Any,
    ont_graph: Any,
    *,
    shape: Any,
    focus_node: Any,
    inference: Any,
    include_targets: bool,
) -> Any:
    """``extract_subgraph()`` on the engine (an ``StarLayerGraph``)."""
    from starlayer.shacl_engine.subgraph import extract_subgraph as engine_extract

    return engine_extract(
        data_graph,
        shacl_graph,
        ont_graph,
        shape=shape,
        focus_node=focus_node,
        inference=inference,
        include_targets=include_targets,
    )


def target_nodes(*, data_graph: Any, shacl_graph: Any, shape_node: Any, ont_graph: Any, inference: Any) -> tuple[Any, ...]:
    """The nodes ``shape_node`` targets in ``data_graph``, as ``validate()`` resolves them."""
    from starlayer.shacl_engine import api

    data, shapes, ont = _normalise(data_graph, shacl_graph if shacl_graph is not None else data_graph, ont_graph)
    return tuple(api.target_nodes(data, shapes, shape_node, ont_graph=ont, inference=inference))


def extract_shapes_graph(shapes_graph: Any, shapes_graph_iri: Any, *, include_referenced: bool) -> Any:
    """``StarShaclSchema.extract_shapes_graph`` on the engine."""
    from starlayer.shacl_engine.shapes_graphs import (
        extract_shapes_graph as engine_extract,
    )

    return engine_extract(shapes_graph, shapes_graph_iri, include_referenced=include_referenced)


def close_shape(shapes_graph: Any, shape: Any) -> Any:
    """``StarShaclSchema.close_shape`` on the engine."""
    from starlayer.shacl_engine.shapes_graphs import close_shape as engine_close

    return engine_close(shapes_graph, shape)
