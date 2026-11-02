"""Opt-in compatibility adapter: run the OLD public SHACL API on the NEW native engine (``starlayer.shacl_engine``).

Stage a of ``docs/working/shacl-engine-cutover.md``. Nothing changes unless asked: every old entry point
(``validate``, ``validate_each``, ``apply_rules``, ``evaluate``, ``extract_subgraph`` and the ``StarShaclSchema`` methods,
plus ``close_shape`` / ``extract_shapes_graph``) starts with a guard that asks :func:`selected` which engine to use and, only
when it says ``"native"``, hands the call to this module.

Selection (:func:`selected`), strongest first:

1. the call's ``engine=`` keyword (``"native"`` or ``"pyshacl"``);
2. while a fallback is running, ``"pyshacl"`` (so the old code's own internal ``validate`` calls stay on one engine);
3. the ``engine=`` default bound on a ``StarShaclSchema``;
4. the ``STARLAYER_SHACL_ENGINE`` environment variable;
5. ``"native"`` (the default since the cut-over; ``"pyshacl"`` stays only as a rollback switch until the old code is deleted).

An option with no native equivalent (``validate_fn``, ``adapter``, ``decode_report=False``, ``iterate_rules``,
``rdfs_subclass_reasoning_includes_shapes_graph``, ``include_source_rule_provenance``, pySHACL-only switches such as
``js``/``sparql_mode``, ``focus_nodes``/``use_shapes``, a non-``StarLayerGraph`` ``apply_rules`` input, an unknown option
that the old code rejects with ``TypeError``) makes the call FALL BACK to the old path: it never raises for that reason and
never silently changes the result. ``ValidationResult.engine`` / ``RulesResult.engine`` say which engine ran and
``engine_fallback_reason`` why a fallback happened; :func:`last_run` gives the same for the entry points that return a bare
graph.

Where the draft and pySHACL differ the engine follows the draft (see ``docs/working/shacl-engine-differential.md``): this
adapter does not try to reproduce the old behaviour.
"""

from __future__ import annotations

import contextlib
import contextvars
import dataclasses
import os
from collections.abc import Callable, Iterator
from typing import Any

from rdflib import BNode, Namespace, URIRef

SH = Namespace("http://www.w3.org/ns/shacl#")  # rdflib terms: the adapter speaks the caller's term model
_RDF_REIFIES = URIRef("http://www.w3.org/1999/02/22-rdf-syntax-ns#reifies")

ENV_VAR = "STARLAYER_SHACL_ENGINE"
NATIVE = "native"
PYSHACL = "pyshacl"
ENGINES = (NATIVE, PYSHACL)

_FORCE_OLD: contextvars.ContextVar[bool] = contextvars.ContextVar("starlayer_shacl_force_pyshacl", default=False)
_LAST_RUN: contextvars.ContextVar[tuple[str, str | None]] = contextvars.ContextVar(
    "starlayer_shacl_last_run", default=(NATIVE, None)
)

# pySHACL-only switches (``pyshacl.validate`` options plus the ``**kwargs`` it ignores): off/None is harmless, anything else
# asks for pySHACL behaviour the engine has no analogue for
_PYSHACL_ONLY_SWITCHES = (
    "js",
    "sparql_mode",
    "do_owl_imports",
    "check_dash_result",
    "focus_nodes",
    "use_shapes",
    "multi_data_graphs_mode",
    "data_graph_format",
    "shacl_graph_format",
    "ont_graph_format",
    "serialize_report_graph",
    "serialize_expanded_graph",
    "serialize_expanded_graph_format",
)


def _ill_formed_reason(exc: Exception) -> str:
    """The recorded fallback reason for a graph the engine rejects with ``TermError``."""
    return f"ill-formed RDF term (the engine validates RDF graphs; pySHACL path used): {str(exc)[:300]}"


class NativeUnsupported(Exception):
    """An option of an old entry point has no native equivalent; the call falls back to pySHACL. ``str(self)`` is the reason."""


_PLAN_CACHE: contextvars.ContextVar[dict | None] = contextvars.ContextVar("starlayer_shacl_plan_cache", default=None)


@contextlib.contextmanager
def shared_plans() -> Iterator[dict]:
    """While active, native validations over the same explicit shapes graph object share one parsed ``Plan`` (used by the
    ``validate_each`` entry points: the shapes are parsed once for the whole batch, not once per data graph)."""
    cache: dict = {}
    token = _PLAN_CACHE.set(cache)
    try:
        yield cache
    finally:
        _PLAN_CACHE.reset(token)


def normalise_engine(engine: Any, *, source: str = "engine") -> str | None:
    """``engine`` as ``"native"`` / ``"pyshacl"`` (case and surrounding space ignored); ``None`` and ``""`` give ``None``."""
    if engine is None:
        return None
    if not isinstance(engine, str):
        raise ValueError(f"{source} must be 'native' or 'pyshacl', not {engine!r}")
    key = engine.strip().lower()
    if not key:
        return None
    if key not in ENGINES:
        raise ValueError(f"{source} must be 'native' or 'pyshacl', not {engine!r}")
    return key


def selected(engine: str | None = None, schema_default: str | None = None) -> str:
    """The engine a call should use: see the module docstring for the precedence."""
    explicit = normalise_engine(engine)
    if explicit is not None:
        return explicit
    if _FORCE_OLD.get():
        return PYSHACL
    bound = normalise_engine(schema_default)
    if bound is not None:
        return bound
    return normalise_engine(os.environ.get(ENV_VAR), source=ENV_VAR) or NATIVE


def last_run() -> tuple[str, str | None]:
    """``(engine, fallback_reason)`` of the most recent adapter-dispatched call in this context (for the entry points whose
    result is a plain graph and so cannot carry the fields)."""
    return _LAST_RUN.get()


def _record(engine: str, reason: str | None) -> None:
    _LAST_RUN.set((engine, reason))


def _stamp(result: Any, engine: str, reason: str | None) -> Any:
    from starlayer.shacl.results import RulesResult, ValidationResult

    if isinstance(result, RulesResult):
        validation = dataclasses.replace(result.validation, engine=engine, engine_fallback_reason=reason)
        return dataclasses.replace(result, validation=validation, engine=engine, engine_fallback_reason=reason)
    if isinstance(result, ValidationResult):
        return dataclasses.replace(result, engine=engine, engine_fallback_reason=reason)
    return result


def _run_old(old: Callable[..., Any], args: tuple, opts: dict[str, Any], reason: str) -> Any:
    """The old pySHACL path for a call the native engine cannot take; ``reason`` is recorded on the result."""
    token = _FORCE_OLD.set(True)
    try:
        result = old(*args, engine=PYSHACL, **opts)
    finally:
        _FORCE_OLD.reset(token)
    _record(PYSHACL, reason)
    return _stamp(result, PYSHACL, reason)


# ---------------------------------------------------------------------------------------------------------------------
# option translation


def conformance_disallows_for(allow_warnings: Any, allow_infos: Any) -> URIRef | None:
    """The engine's ``conformance_disallows`` (the lowest severity that blocks conformance) for the old
    ``allow_warnings`` / ``allow_infos``: allowing warnings also allows infos (only violations block); allowing infos alone
    lets Info through (Warning and Violation block); neither: ``None`` (Info and above block, the draft's default)."""

    if allow_warnings:
        return SH.Violation
    if allow_infos:
        return SH.Warning
    return None


def translate_validate_options(options: dict[str, Any], *, explicit_iterate_rules: bool = False) -> dict[str, Any]:
    """Map the resolved old option dict (mode preset plus overrides) to ``shacl_engine.validate`` keywords.

    Raises :class:`NativeUnsupported` for an option with no native equivalent. ``advanced`` False means no rule execution
    (``rules=False``); the ``"rules"`` preset (``iterate_rules``) means ``rules=True``; otherwise ``rules=None``, which runs
    rules only when the shapes graph declares ``sh:entailment`` (the draft, see the differential doc). ``debug`` is
    ignored (it only affects pySHACL's logging)."""
    if explicit_iterate_rules and options.get("iterate_rules"):
        raise NativeUnsupported("iterate_rules (the engine runs the draft's rule iteration; no pySHACL-style option)")
    for name in _PYSHACL_ONLY_SWITCHES:
        if options.get(name) not in (None, False):
            raise NativeUnsupported(f"{name} (a pySHACL-only option with no native equivalent)")
    out: dict[str, Any] = {}
    out["conformance_disallows"] = conformance_disallows_for(options.get("allow_warnings"), options.get("allow_infos"))
    out["inplace"] = bool(options.get("inplace"))
    out["abort_on_first"] = bool(options.get("abort_on_first") or options.get("abort_on_error"))
    depth = options.get("max_validation_depth")
    if depth is not None:
        out["max_validation_depth"] = depth
    meta = options.get("meta_shacl")
    if meta:
        out["meta_shacl"] = meta
    if options.get("advanced") is False:
        out["rules"] = False
    elif options.get("iterate_rules"):
        out["rules"] = True
    else:
        out["rules"] = None
    return out


def _reject_unknown(kwargs: dict[str, Any]) -> None:
    """The old validator's ``TypeError`` for an option nobody knows (a typo), kept identical."""
    from starlayer.shacl.validator import (
        _default_validate,
        _reject_unknown_validate_options,
    )

    _reject_unknown_validate_options(kwargs, _default_validate)


def _check_imports(shapes: Any, loader: Any, ignore_imports: bool) -> None:
    """The old default: ``owl:imports`` that are not locally satisfied and no loader and not ``ignore_imports`` is an error
    (the engine resolves imports only when a loader is given)."""
    if shapes is not None and loader is None and not ignore_imports:
        from starlayer.shacl_engine.imports import resolve_imports

        resolve_imports(shapes, None, False)


def _normalise(data: Any, shapes: Any, ont: Any) -> tuple[Any, Any, Any]:
    from starlayer.shacl.engine import normalize_graph_inputs

    return normalize_graph_inputs(data, shapes, ont)


def _meta_preflight(shapes: Any, meta_shapes_extra: Any, floor: Any) -> None:
    """The ``meta_shacl=True`` preflight on the shapes graph, run here so the old call-site semantics hold: the caller's
    ``allow_warnings`` / ``allow_infos`` relax it too (the engine's own default tolerates Warning and Info), and the SPARQL
    text check of the old preflight follows it."""
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
    """``sh:conformanceDisallows`` as the old validator writes it: always the explicit set of blocking severities
    (Violation; Warning unless warnings are allowed; Info unless warnings or infos are allowed), where the engine writes the
    property only for a non-default floor."""
    from rdflib.namespace import RDF


    node = next(report.subjects(RDF.type, SH.ValidationReport), None)
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
    old: Callable[..., Any],
    old_args: tuple,
    old_opts: dict[str, Any],
    *,
    data_graph: Any,
    shacl_graph: Any,
    ont_graph: Any,
    inference: Any = None,
    mode: Any = None,
    kwargs: dict[str, Any],
    decode_report: bool = True,
    rdfs_subclass_reasoning_includes_shapes_graph: bool = False,
    custom_validate_fn: bool = False,
    custom_adapter: bool = False,
    shapes_graph_loader: Any = None,
    ignore_imports: bool = False,
    meta_shapes_extra: Any = (),
    data_graph_iri: Any = None,
    shapes_graph_iri: Any = None,
    shapes_graph_resource: Any = None,
    specification_graph: Any = None,
    include_used_configuration: bool = False,
) -> Any:
    """``validate()`` on the native engine, or ``old(*old_args, engine='pyshacl', **old_opts)`` when it cannot.

    ``old`` is the old function or bound method the guard sits in; ``old_args``/``old_opts`` replay the call. ``kwargs`` is the
    old ``**kwargs`` (option overrides); ``inference`` is the module-level keyword, or ``self.inference`` for the schema
    (which also rejects ``inference`` in ``kwargs``)."""
    reason = _validate_unsupported(
        kwargs, decode_report, rdfs_subclass_reasoning_includes_shapes_graph, custom_validate_fn, custom_adapter
    )
    if reason is not None:
        return _run_old(old, old_args, old_opts, reason)
    from starlayer.shacl.validation_modes import resolve_mode_options

    # errors the old path raises for a bad call are raised by it, identically
    _reject_unknown(kwargs)
    resolved = resolve_mode_options(mode, overrides=kwargs)
    inference = resolved.get("inference", inference) if "inference" in kwargs else inference
    try:
        engine_kwargs = translate_validate_options(resolved, explicit_iterate_rules="iterate_rules" in kwargs)
    except NativeUnsupported as exc:
        return _run_old(old, old_args, old_opts, str(exc))
    from starlayer.shacl_engine.terms import TermError

    try:
        return _validate_native(
            data_graph,
            shacl_graph,
            ont_graph,
            engine_kwargs,
            inference=inference,
            shapes_graph_loader=shapes_graph_loader,
            ignore_imports=ignore_imports,
            meta_shapes_extra=meta_shapes_extra,
            data_graph_iri=data_graph_iri,
            shapes_graph_iri=shapes_graph_iri,
            shapes_graph_resource=shapes_graph_resource,
            specification_graph=specification_graph,
            include_used_configuration=include_used_configuration,
        )
    except TermError as exc:
        # A graph with a term that is not an RDF term (relative IRI ...) is outside SHACL 1.2's domain, so the engine rejects
        # it up front, before it writes anything. The old API accepted such graphs and pySHACL defines their result, so the
        # call falls back there (the reason is on ``ValidationResult.engine_fallback_reason``).
        return _run_old(old, old_args, old_opts, _ill_formed_reason(exc))


def _validate_unsupported(
    kwargs: dict[str, Any],
    decode_report: bool,
    rdfs_subclass: bool,
    custom_validate_fn: bool,
    custom_adapter: bool,
) -> str | None:
    if custom_validate_fn:
        return "validate_fn (a custom validation callable runs pySHACL-style, not on the engine)"
    if custom_adapter:
        return "adapter (a custom TripleTermAdapter: the engine handles triple terms natively)"
    if not decode_report:
        return "decode_report=False (the engine never encodes triple terms, so there is no encoded report)"
    if rdfs_subclass:
        return "rdfs_subclass_reasoning_includes_shapes_graph (the draft reads classes from the data graph only)"
    return None


def _validate_native(
    data_graph: Any,
    shacl_graph: Any,
    ont_graph: Any,
    engine_kwargs: dict[str, Any],
    *,
    inference: Any,
    shapes_graph_loader: Any,
    ignore_imports: bool,
    meta_shapes_extra: Any,
    data_graph_iri: Any,
    shapes_graph_iri: Any,
    shapes_graph_resource: Any,
    specification_graph: Any,
    include_used_configuration: bool,
) -> Any:
    from starlayer.shacl.results import ValidationResult
    from starlayer.shacl_engine import api

    original = data_graph
    data, shapes, ont = _normalise(data_graph, shacl_graph, ont_graph)
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
    _check_imports(shapes, shapes_graph_loader, ignore_imports)
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
        plan_cache=_PLAN_CACHE.get(),
        **engine_kwargs,
    )
    _annotate_conformance_disallows(outcome.report_graph, engine_kwargs.get("conformance_disallows"))
    out_data = None
    if engine_kwargs.get("inplace"):
        out_data = original
        if data is not original:  # a plain graph was converted: write the inferred triples back, as the old code did
            for t in list(data.triples((None, None, None))):
                if t not in original:
                    original.add(t)
    _record(NATIVE, None)
    return ValidationResult(
        conforms=outcome.conforms,
        report_graph=outcome.report_graph,
        report_text=outcome.report_text,
        data_graph=out_data,
        diagnostics=outcome.diagnostics,
        engine=NATIVE,
        engine_fallback_reason=None,
    )


# ---------------------------------------------------------------------------------------------------------------------
# apply_rules


def _rule_set_iris(rule_set: Any) -> list[Any] | None:
    if rule_set is None:
        return None
    if isinstance(rule_set, (str, URIRef)) or not hasattr(rule_set, "__iter__"):
        members = [rule_set]
    else:
        members = list(rule_set)
    return [URIRef(m) if type(m) is str else m for m in members]  # a plain string is an IRI, as it was for the old validator


def apply_rules(
    old: Callable[..., Any],
    old_args: tuple,
    old_opts: dict[str, Any],
    *,
    data_graph: Any,
    shacl_graph: Any,
    ont_graph: Any,
    include_source_rule_provenance: bool,
    rule_set: Any,
    kwargs: dict[str, Any],
) -> Any:
    """``apply_rules()`` on the native engine (``RulesResult``), or the old path when it cannot."""
    from starlayer.shacl.results import RulesResult
    from starlayer.shacl.validator import _is_starlayer_graph, _oxigraph_to_starlayer
    from starlayer.shacl_engine import api, rules
    from starlayer.shacl_engine.entailment import resolve_data_view

    data_graph = _oxigraph_to_starlayer(data_graph)
    shacl_graph = _oxigraph_to_starlayer(shacl_graph)
    ont_graph = _oxigraph_to_starlayer(ont_graph)
    if not _is_starlayer_graph(data_graph):
        return _run_old(old, old_args, old_opts, "data_graph is not a StarLayerGraph (the old call raises TypeError)")
    from starlayer.shacl.validation_modes import resolve_mode_options

    # the old apply_rules forwards its **kwargs to validate(), so validate()'s own keywords are accepted here too
    kwargs = dict(kwargs)
    passthrough = {
        name: kwargs.pop(name)
        for name in (
            "data_graph_iri",
            "shapes_graph_iri",
            "shapes_graph_resource",
            "specification_graph",
            "include_used_configuration",
            "ignore_imports",
            "shapes_graph_loader",
            "meta_shapes_extra",
        )
        if name in kwargs
    }
    reason = _validate_unsupported(
        kwargs,
        kwargs.pop("decode_report", True),
        kwargs.pop("rdfs_subclass_reasoning_includes_shapes_graph", False),
        kwargs.pop("validate_fn", None) is not None,
        kwargs.pop("adapter", None) is not None,
    )
    if reason is not None:
        return _run_old(old, old_args, old_opts, reason)
    mode = kwargs.pop("mode", None)
    _reject_unknown(kwargs)
    final_options = resolve_mode_options("validation", overrides=kwargs)
    try:
        engine_kwargs = translate_validate_options(final_options, explicit_iterate_rules="iterate_rules" in kwargs)
    except NativeUnsupported as exc:
        return _run_old(old, old_args, old_opts, str(exc))
    del mode
    from starlayer.shacl_engine.terms import TermError

    try:
        engine_kwargs.pop("inplace", None)
        engine_kwargs["rules"] = False  # the rules have run: the final pass validates the evaluation graph only
        inference = kwargs.get("inference")
        data, shapes, ont = _normalise(data_graph, shacl_graph if shacl_graph is not None else data_graph, ont_graph)
        # "before rules" entailment pass: the rules see the entailed graph (kept as an overlay; entailed triples are not inferred)
        base = resolve_data_view(data, shapes, inference=inference, ont_graph=ont)
        result = rules.apply_rules(
            base, shapes, rule_sets=_rule_set_iris(rule_set), source_rules=bool(include_source_rule_provenance)
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
        from starlayer.shacl.results import ValidationResult

        _annotate_conformance_disallows(outcome.report_graph, engine_kwargs.get("conformance_disallows"))
        validation = ValidationResult(
            conforms=outcome.conforms,
            report_graph=outcome.report_graph,
            report_text=outcome.report_text,
            data_graph=None,
            diagnostics=outcome.diagnostics,
            engine=NATIVE,
        )
        inferred = type(data)()
        for prefix, ns in data.namespaces():
            inferred.bind(prefix, ns)
        for t in result.inferred:
            inferred.add(t)
        for triple, rule_node in result.source_rules:  # SHACL 1.2 Inference Rules 9: _:r rdf:reifies <<( s p o )>> ; sh:sourceRule <rule>
            reifier = BNode()
            inferred.add((reifier, _RDF_REIFIES, triple))  # a plain 3-tuple is a triple term in object position
            inferred.add((reifier, SH.sourceRule, rule_node))
    except TermError as exc:  # see validate(): the engine rejects non-RDF terms up front; the old path takes the call
        return _run_old(old, old_args, old_opts, _ill_formed_reason(exc))
    _record(NATIVE, None)
    return RulesResult(inferred_graph=inferred, validation=validation, engine=NATIVE)


# ---------------------------------------------------------------------------------------------------------------------
# evaluate / extract_subgraph / shapes-graph helpers


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
    """``evaluate()`` on the native engine (a plain graph)."""
    from starlayer.shacl_engine.evaluate import evaluate as engine_evaluate

    data, shapes, ont = _normalise(data_graph, shacl_graph if shacl_graph is not None else data_graph, ont_graph)
    result = engine_evaluate(
        data,
        shapes,
        ont,
        inference=inference,
        focus_nodes=focus_nodes,
        properties=properties,
        rules_entailment=rules_entailment,
    )
    _record(NATIVE, None)
    return result


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
    """``extract_subgraph()`` on the native engine (a ``StarLayerGraph``)."""
    from starlayer.shacl_engine.subgraph import extract_subgraph as engine_extract

    result = engine_extract(
        data_graph,
        shacl_graph,
        ont_graph,
        shape=shape,
        focus_node=focus_node,
        inference=inference,
        include_targets=include_targets,
    )
    _record(NATIVE, None)
    return result


def extract_shapes_graph(shapes_graph: Any, shapes_graph_iri: Any, *, include_referenced: bool) -> Any:
    """``StarShaclSchema.extract_shapes_graph`` on the native engine."""
    from starlayer.shacl_engine.shapes_graphs import (
        extract_shapes_graph as engine_extract,
    )

    result = engine_extract(shapes_graph, shapes_graph_iri, include_referenced=include_referenced)
    _record(NATIVE, None)
    return result


def close_shape(shapes_graph: Any, shape: Any) -> Any:
    """``StarShaclSchema.close_shape`` / ``_close_shape`` on the native engine."""
    from starlayer.shacl_engine.shapes_graphs import close_shape as engine_close

    result = engine_close(shapes_graph, shape)
    _record(NATIVE, None)
    return result


__all__ = [
    "ENGINES",
    "ENV_VAR",
    "NATIVE",
    "PYSHACL",
    "NativeUnsupported",
    "conformance_disallows_for",
    "last_run",
    "normalise_engine",
    "selected",
    "translate_validate_options",
]
