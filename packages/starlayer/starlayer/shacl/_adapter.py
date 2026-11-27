"""The public SHACL entry points (``validate``, ``apply_rules``, ``evaluate``, ``extract_subgraph``, ...) on the native engine
(``starlayer.shacl.engine``): graph normalisation, option translation and result shaping.

An option the engine has no use for is a ``TypeError`` (an unknown keyword), as is a misspelt one. The engine follows the SHACL 1.2
drafts where the earlier validator differed; see ``docs/working/shacl-engine-differential.md``.
"""

from __future__ import annotations

import contextlib
import contextvars
from collections.abc import Iterator
from typing import Any

import pyoxigraph as ox

from starlayer._callsite import warn_at_caller
from starlayer.shacl.engine.terms import RDF, SH, to_engine

_RDF_REIFIES = RDF.reifies


# The keywords ``validate()`` takes besides its named parameters: the option presets of
# ``validation_modes`` and their per-call overrides. ``rules`` is the engine's own switch (``None``: run rules only when the shapes
# declare ``sh:entailment``; ``True``: always; ``False``: never). ``advanced`` is deprecated (``advanced=False`` meant ``rules=False``,
# ``advanced=True`` nothing); ``debug`` is accepted and ignored.
VALIDATE_OPTIONS = frozenset(
    {
        "advanced",
        "rules",
        "debug",
        "inplace",
        "meta_shacl",
        "allow_warnings",
        "allow_infos",
        "abort_on_first",
        "abort_on_error",
        "inference",
        "engine",
        "timeout",
        "recompute",
        "subclass_of_in_shapes_graph",
    }
)

_PLAN_CACHE: contextvars.ContextVar[dict | None] = contextvars.ContextVar("starlayer_shacl_plan_cache", default=None)


@contextlib.contextmanager
def shared_plans(cache: dict | None = None) -> Iterator[dict]:
    """While active, validations over the same explicit shapes graph object share one parsed ``Plan`` (used by the
    ``validate_each`` entry points: the shapes are parsed once for the whole batch, not once per data graph). A caller that owns
    a shapes graph it never changes (the ``sqe:`` and ``srl:`` shapes) passes a ``cache`` dict it keeps, so the Plan lives as
    long as the dict and is built once per process."""
    cache = {} if cache is None else cache
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
    """Map the resolved option dict (mode preset plus overrides) to ``shacl.engine.validate`` keywords. ``rules`` passes through
    (``None``: run rules only when the shapes graph declares ``sh:entailment``, the draft's default; ``True``: always, as the
    ``"rules"`` preset does; ``False``: never). The deprecated ``advanced`` warns; ``advanced=False`` means ``rules=False`` unless
    ``rules`` is also given, which then wins."""
    out: dict[str, Any] = {}
    out["conformance_disallows"] = conformance_disallows_for(options.get("allow_warnings"), options.get("allow_infos"))
    out["inplace"] = bool(options.get("inplace"))
    out["abort_on_first"] = bool(options.get("abort_on_first") or options.get("abort_on_error"))
    if options.get("subclass_of_in_shapes_graph"):
        out["subclass_of_in_shapes_graph"] = True
    for name in ("engine", "timeout", "recompute"):  # entailment: the engine's own defaults apply when not given
        if options.get(name) is not None:
            out[name] = options[name]
    meta = options.get("meta_shacl")
    if meta:
        out["meta_shacl"] = meta
    rules = options.get("rules")
    if "advanced" in options:
        _warn_advanced_deprecated()
        if options["advanced"] is False and rules is None:
            rules = False
    out["rules"] = rules
    return out


def _warn_advanced_deprecated() -> None:
    """A ``DeprecationWarning`` that points at the first frame outside this package (the caller's line)."""
    warn_at_caller(
        "the validate option advanced= is deprecated: use rules=False instead of advanced=False (no rule execution); "
        "advanced=True is the default and can be left out",
        DeprecationWarning,
    )


# Engine limits that the public functions do not take (decision 2026-11-24): the engine keeps them as parameters
# (``engine.api.validate(max_validation_depth=)``).
_INTERNAL_LIMITS = frozenset({"max_validation_depth"})


def _reject_internal_limits(options: Any) -> None:
    refused = sorted(set(options) & _INTERNAL_LIMITS)
    if refused:
        raise TypeError(f"{', '.join(refused)} is not an option of the public validate(), validate_each() and apply_rules(): it is an internal engine limit")


def check_max_triples(value: Any) -> None:
    """``TypeError`` unless ``max_triples`` is ``None`` (no cap) or an ``int``; ``ValueError`` for a negative one."""
    if value is None:
        return
    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError(f"max_triples must be an int or None (no cap), not {value!r}")
    if value < 0:
        raise ValueError(f"max_triples must not be negative, not {value!r}")


def check_max_iterations(value: Any) -> None:
    """``TypeError`` unless ``max_iterations`` is an ``int`` (``None`` is not "unlimited"; the constructor reads it as "use the
    default"); ``ValueError`` for a negative one. Zero is allowed."""
    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError(f"max_iterations must be an int, not {value!r}")
    if value < 0:
        raise ValueError(f"max_iterations must not be negative, not {value!r}")


def reject_unknown_options(kwargs: dict[str, Any]) -> None:
    """``TypeError`` for an option nobody knows (a typo, or a keyword of the validator this one replaced)."""
    _reject_internal_limits(kwargs)
    unknown = sorted(set(kwargs) - VALIDATE_OPTIONS)
    if unknown:
        raise TypeError(
            f"unknown option(s) {', '.join(unknown)}; the options are {', '.join(sorted(VALIDATE_OPTIONS))} "
            "(inference is an entailment regime IRI, ENTAILMENT.RDFS for example)"
        )


def _check_imports(shapes: Any, loader: Any, ignore_imports: bool | None) -> None:
    """The shapes graph's ``owl:imports`` (the graph's own loader and flag, overridden by the call's) are resolved or the call raises
    ``ExecutionError`` kind ``"import"`` before the meta preflight runs; ``engine.api.validate`` asks again and finds the kept result."""
    if shapes is not None:
        from starlayer.shacl.engine.imports import resolve_imports

        resolve_imports(shapes, loader, ignore_imports)


def _normalise(data: Any, shapes: Any, ont: Any) -> tuple[Any, Any, Any]:
    """The three graphs as Oxigraph-backed graphs (an rdflib graph is a ``TypeError``)."""
    from starlayer.shacl.normalization import normalize_graph_inputs

    return normalize_graph_inputs(data, shapes, ont)


def _meta_preflight(shapes: Any, meta_shapes_extra: Any) -> None:
    """The ``meta_shacl=True`` preflight on the shapes graph. Strict whatever ``allow_warnings`` / ``allow_infos`` say (those
    describe the data validation, and the shapes-about-shapes warnings are not meant to be ignored: the W3C SHACL-for-SHACL says to
    deactivate the shape instead; pySHACL's meta check is strict too). The defects of the embedded SPARQL text are part of the same error."""
    from starlayer.shacl.engine.meta import meta_validate

    meta_validate(
        shapes,
        meta_shacl=True,
        meta_shapes_extra=meta_shapes_extra,
    )


class CheckedShapes:
    """What a ``StarShaclProcessor`` found out about its shapes graph at construction: the compiled ``Plan`` and the meta-SHACL
    results, so ``validate()`` does not read or check the same shapes again.

    Both are tied to a fingerprint of the shapes graph's triples (``graph.entailment.cache.content_fingerprint``: a count and a hash of the set),
    taken again on each ``validate()``: a shapes graph the caller changed after construction is compiled and checked again, at
    that call (a ``ShapeError`` then comes from ``validate()``)."""

    def __init__(self) -> None:
        self.fingerprint: Any = None
        self.plan: Any = None
        self._meta_ok: set = set()

    @staticmethod
    def _fingerprint(graph: Any) -> Any:
        from starlayer.graph.entailment.cache import content_fingerprint
        from starlayer.shacl.engine.terms import engine_view

        return content_fingerprint(engine_view(graph, "shapes graph").triples((None, None, None)))

    def compile(self, shapes: Any, resolved: Any = None) -> None:
        """Compile the plan over ``resolved`` (the shapes with their imports; default ``shapes``) and remember ``shapes``'
        fingerprint. ``ShapeError`` from reading the shapes leaves the previous state in place."""
        from starlayer.shacl.engine.plan import Plan

        fingerprint = self._fingerprint(shapes)
        plan = Plan(shapes_graph=shapes if resolved is None else resolved).compile()
        self.fingerprint, self.plan = fingerprint, plan

    def plan_for(self, shapes: Any) -> Any:
        """The compiled plan of ``shapes``, compiled again first if its triples changed since; ``None`` when no plan was compiled
        at construction (the engine then builds its own)."""
        if self.plan is None:
            return None
        if self._fingerprint(shapes) != self.fingerprint:
            self.compile(shapes)
        return self.plan

    def check_meta(self, shapes: Any, meta_shapes_extra: Any) -> None:
        """``_meta_preflight`` unless this shapes graph (with these extras) already passed it."""
        extras = tuple(meta_shapes_extra)
        key = (self._fingerprint(shapes), tuple((id(x), self._fingerprint(x)) for x in extras))
        if key not in self._meta_ok:
            _meta_preflight(shapes, extras)
            self._meta_ok.add(key)  # only a pass is kept: a failing graph raises again on the next call


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
    option_defaults: dict[str, Any] | None = None,
    imports_loader: Any = None,
    ignore_imports: bool | None = None,
    meta_shapes_extra: Any = (),
    data_graph_iri: Any = None,
    shapes_graph_iri: Any = None,
    shapes_graph_resource: Any = None,
    specification_graph: Any = None,
    include_used_configuration: bool = False,
    build: str | None = None,
    checked: CheckedShapes | None = None,
    engine_limits: dict[str, Any] | None = None,
) -> Any:
    """``validate()`` on the engine: a ``ValidationReport``. ``options`` is the caller's ``**kwargs`` (option overrides);
    ``inference`` is the keyword of ``validate()``, or the schema's bound regime.
    ``option_defaults`` are a processor's constructor options: below the ``mode`` preset, which is below ``options``.
    ``checked`` is a processor's ``CheckedShapes``: its compiled plan and meta-SHACL result are reused for its shapes graph.
    ``engine_limits`` are engine parameters the public functions do not take (``max_validation_depth``), for callers inside
    the package that validate their own shapes (:func:`validate_bounded`)."""
    from starlayer.shacl.engine import api
    from starlayer.shacl.results import ValidationReport
    from starlayer.shacl.validation_modes import resolve_mode_options

    reject_unknown_options(options)
    resolved = resolve_mode_options(mode, overrides=options, defaults=option_defaults)
    inference = resolved.get("inference", inference) if "inference" in options else inference
    engine_kwargs = translate_validate_options(resolved)
    engine_kwargs.update(engine_limits or {})

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
            "construct with StarShaclProcessor(shacl_graph=...). (If you only "
            "want to record where the shapes came from, pass shapes_graph_iri=.)"
        )
    _check_imports(shapes if shapes is not None else data, imports_loader, ignore_imports)
    meta_shacl = engine_kwargs.pop("meta_shacl", None)
    if checked is not None and shapes is not None:
        if meta_shacl:
            checked.check_meta(shapes, meta_shapes_extra)
        prebuilt_plan = checked.plan_for(shapes)
    else:
        prebuilt_plan = None
        if meta_shacl:
            _meta_preflight(shapes if shapes is not None else data, meta_shapes_extra)
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
        build=build,
        imports_loader=imports_loader,
        ignore_imports=ignore_imports,
        meta_shapes_extra=meta_shapes_extra,
        plan_cache=cache,
        prebuilt_plan=prebuilt_plan,
        configuration_extra=_preflight_configuration(meta_shacl, imports_loader, meta_shapes_extra),
        **engine_kwargs,
    )
    floor = engine_kwargs.get("conformance_disallows")
    outcome.after_report_graph(lambda graph: _annotate_conformance_disallows(graph, floor))  # (when the graph is written: now if it was asked for)
    out_data = None
    if engine_kwargs.get("inplace"):
        out_data = original
        if data is not original:  # a graph was converted (or a Store wrapped): write the inferred triples back
            api._write_back(data, original)
    return ValidationReport(
        conforms=outcome.conforms,
        report_graph=lambda: outcome.report_graph,
        report_text=lambda: outcome.report_text,
        data_graph=out_data,
        diagnostics=lambda: outcome.diagnostics,
    )


def validate_bounded(
    data_graph: Any, shacl_graph: Any, *, ont_graph: Any = None, inference: Any = None, max_validation_depth: int, allow_warnings: bool = False
) -> Any:
    """:func:`validate` with an explicit shape-nesting bound, for the package's own checks of its fixed shapes (``sqe:``, SRL,
    Manchester syntax), which the public ``starlayer.shacl.validate()`` no longer lets a caller set. With ``allow_warnings`` a
    result of ``sh:Warning`` severity is reported but does not make the report non-conforming (a note for the reader, not a fault)."""
    return validate(
        data_graph=data_graph,
        shacl_graph=shacl_graph,
        ont_graph=ont_graph,
        inference=inference,
        options={"allow_warnings": True} if allow_warnings else {},
        engine_limits={"max_validation_depth": max_validation_depth},
        build="graph",  # (every one of those checks reads or adds to the report graph)
    )


# ---------------------------------------------------------------------------------------------------------------------
# apply_rules


def _preflight_configuration(meta_shacl: Any, imports_loader: Any, meta_shapes_extra: Any) -> dict[str, Any]:
    """The settings of the checks made before the engine runs (the meta-SHACL check and the import loader), for the run's
    configuration record: the engine never sees ``meta_shacl`` here, it is popped for the preflight."""
    extra: dict[str, Any] = {"metaShacl": bool(meta_shacl)}
    if imports_loader is not None:
        extra["shapesGraphLoader"] = True
    count = len(list(meta_shapes_extra or ()))
    if count:
        extra["metaShapesExtra"] = count
    return extra


def _rule_set_iris(rule_set: Any) -> list[Any] | None:
    if rule_set is None:
        return None
    if isinstance(rule_set, (str, ox.NamedNode)) or not hasattr(rule_set, "__iter__"):
        members = [rule_set]
    else:
        members = list(rule_set)
    return [ox.NamedNode(m) if type(m) is str else to_engine(m) for m in members]  # a plain string is an IRI


# The keywords ``apply_rules()`` takes besides its named parameters: what rule execution still uses. ``rules`` / ``advanced`` /
# ``debug`` / ``inplace`` are not among them (the rules always run, on an overlay, and nothing is validated or written back).
RULES_OPTIONS = frozenset(
    {
        "inference",
        "engine",
        "timeout",
        "recompute",
        "subclass_of_in_shapes_graph",
        "meta_shacl",
        "meta_shapes_extra",
        "ignore_imports",
        "imports_loader",
        "max_iterations",
        "max_triples",
    }
)

# Keywords of ``validate()`` that ``apply_rules()`` refuses with a message that says so (the closed-set ``TypeError`` otherwise).
_VALIDATE_ONLY = (
    VALIDATE_OPTIONS
    | {"data_graph_iri", "shapes_graph_iri", "shapes_graph_resource", "specification_graph", "include_used_configuration", "build"}
) - RULES_OPTIONS


def reject_options_for_rules(options: dict[str, Any]) -> None:
    """``TypeError`` for a keyword ``apply_rules()`` does not take: one that only ``validate()`` uses says so (the rules are not
    followed by a validation any more), any other is an unknown option."""
    _reject_internal_limits(options)
    refused = sorted(set(options) & _VALIDATE_ONLY)
    if refused:
        raise TypeError(
            f"apply_rules() does not take {', '.join(refused)}: it only runs the rules and validates nothing, so "
            "the option belongs to validate() (validate(data, shapes, rules=True) runs the rules and then validates, or validate "
            "the data together with result.inferred_graph against the shapes you choose)"
        )
    unknown = sorted(set(options) - RULES_OPTIONS)
    if unknown:
        raise TypeError(
            f"unknown option(s) {', '.join(unknown)}; the options of apply_rules() are {', '.join(sorted(RULES_OPTIONS))} "
            "(inference is an entailment regime IRI, ENTAILMENT.RDFS for example)"
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
    from starlayer.shacl.engine import rules
    from starlayer.shacl.engine.entailment import resolve_data_view
    from starlayer.shacl.results import RulesResult

    reject_options_for_rules(options)
    rule_limits = {name: options[name] for name in ("max_iterations", "max_triples") if name in options}
    if "max_iterations" in rule_limits:
        check_max_iterations(rule_limits["max_iterations"])
    if "max_triples" in rule_limits:
        check_max_triples(rule_limits["max_triples"])
    data, shapes, ont = _normalise(
        data_graph, shacl_graph if shacl_graph is not None else data_graph, ont_graph
    )
    if options.get("meta_shacl"):  # the same preflight as validate(), on the shapes graph as given
        _meta_preflight(shapes, options.get("meta_shapes_extra") or ())
    from starlayer.shacl.engine.imports import resolve_inputs

    # the rules of an imported module run too: imports first, as validate() does (the graphs' own settings, the call's override them)
    shapes, ont = resolve_inputs(
        data, shapes, ont, imports_loader=options.get("imports_loader"), ignore_imports=options.get("ignore_imports")
    )
    # the rules see the entailed graph (kept as an overlay; entailed triples are not inferred)
    base = resolve_data_view(
        data,
        shapes,
        inference=options.get("inference"),
        ont_graph=ont,
        engine=options.get("engine") or "hermit",
        timeout=options.get("timeout"),
        recompute=options.get("recompute") or "onChange",
    )
    result = rules.apply_rules(
        base,
        shapes,
        rule_sets=_rule_set_iris(rule_set),
        source_rules=bool(include_source_rule_provenance),
        subclass_of_in_shapes_graph=bool(options.get("subclass_of_in_shapes_graph")),
        **rule_limits,
    )
    from starlayer.shacl.engine.graphs import new_graph

    inferred = new_graph(data)
    inferred.extend(list(result.inferred))
    for triple, rule_node in result.source_rules:  # SHACL 1.2 Inference Rules 9: _:r rdf:reifies <<( s p o )>> ; sh:sourceRule <rule>
        reifier = ox.BlankNode()
        inferred.add((reifier, _RDF_REIFIES, ox.Triple(*triple)))
        inferred.add((reifier, SH.sourceRule, rule_node))
    return RulesResult(inferred_graph=inferred)


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
    validate: bool = False,
    engine: str = "hermit",
    timeout: Any = None,
    recompute: str = "onChange",
    imports_loader: Any = None,
    ignore_imports: bool | None = None,
) -> Any:
    """``evaluate()`` on the engine (a plain graph)."""
    from starlayer.shacl.engine.evaluate import evaluate as engine_evaluate

    data, shapes, ont = _normalise(data_graph, shacl_graph if shacl_graph is not None else data_graph, ont_graph)
    return engine_evaluate(
        data,
        shapes,
        ont,
        inference=inference,
        engine=engine,
        timeout=timeout,
        recompute=recompute,
        focus_nodes=focus_nodes,
        properties=properties,
        rules_entailment=rules_entailment,
        validate=validate,
        imports_loader=imports_loader,
        ignore_imports=ignore_imports,
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
    imports_loader: Any = None,
    ignore_imports: bool | None = None,
) -> Any:
    """``extract_subgraph()`` on the engine (an ``StarLayerGraph``)."""
    from starlayer.shacl.engine.subgraph import extract_subgraph as engine_extract

    return engine_extract(
        data_graph,
        shacl_graph,
        ont_graph,
        shape=shape,
        focus_node=focus_node,
        inference=inference,
        include_targets=include_targets,
        imports_loader=imports_loader,
        ignore_imports=ignore_imports,
    )


def target_nodes(
    *,
    data_graph: Any,
    shacl_graph: Any,
    shape_node: Any,
    ont_graph: Any,
    inference: Any,
    subclass_of_in_shapes_graph: bool = False,
    engine: str = "hermit",
    timeout: Any = None,
    recompute: str = "onChange",
    imports_loader: Any = None,
    ignore_imports: bool | None = None,
) -> tuple[Any, ...]:
    """The nodes ``shape_node`` targets in ``data_graph``, as ``validate()`` resolves them."""
    from starlayer.shacl.engine import api

    data, shapes, ont = _normalise(data_graph, shacl_graph if shacl_graph is not None else data_graph, ont_graph)
    return tuple(
        api.target_nodes(
            data,
            shapes,
            shape_node,
            ont_graph=ont,
            inference=inference,
            engine=engine,
            timeout=timeout,
            recompute=recompute,
            subclass_of_in_shapes_graph=subclass_of_in_shapes_graph,
            imports_loader=imports_loader,
            ignore_imports=ignore_imports,
        )
    )


def target_shapes(
    *,
    data_graph: Any,
    shacl_graph: Any,
    node: Any,
    ont_graph: Any,
    inference: Any,
    subclass_of_in_shapes_graph: bool = False,
    engine: str = "hermit",
    timeout: Any = None,
    recompute: str = "onChange",
    imports_loader: Any = None,
    ignore_imports: bool | None = None,
) -> tuple[Any, ...]:
    """The shapes that target ``node`` in ``data_graph``, as ``validate()`` resolves them."""
    from starlayer.shacl.engine import api

    data, shapes, ont = _normalise(data_graph, shacl_graph if shacl_graph is not None else data_graph, ont_graph)
    return tuple(
        api.target_shapes(
            data,
            shapes,
            node,
            ont_graph=ont,
            inference=inference,
            engine=engine,
            timeout=timeout,
            recompute=recompute,
            subclass_of_in_shapes_graph=subclass_of_in_shapes_graph,
            imports_loader=imports_loader,
            ignore_imports=ignore_imports,
        )
    )


def candidate_values(
    *,
    data_graph: Any,
    shacl_graph: Any,
    property_shape: Any,
    focus: Any,
    only_valid: bool,
    subclass_of_in_shapes_graph: bool,
    conformance_disallows: Any = None,
) -> Any:
    """``candidate_values()`` on the engine: a ``Candidates``."""
    from starlayer.shacl.candidates import Candidates
    from starlayer.shacl.engine import candidates

    data, shapes, _ont = _normalise(data_graph, shacl_graph if shacl_graph is not None else data_graph, None)
    kind, values, closed, entry = candidates.candidates(
        data,
        shapes,
        property_shape,
        focus=focus,
        only_valid=only_valid,
        subclass_of_in_shapes_graph=subclass_of_in_shapes_graph,
        conformance_disallows=conformance_disallows,
    )
    return Candidates(kind=kind, values=values, closed=closed, entry=entry)


def value_form(*, shacl_graph: Any, property_shape: Any) -> str:
    """``value_form()`` on the engine."""
    from starlayer.shacl.engine import value_form as engine_value_form

    _data, shapes, _ont = _normalise(shacl_graph, shacl_graph, None)
    return engine_value_form.value_form(shapes, property_shape)


def check_value(
    *,
    data_graph: Any,
    shacl_graph: Any,
    property_shape: Any,
    focus: Any,
    value: Any,
    subclass_of_in_shapes_graph: bool = False,
    conformance_disallows: Any = None,
) -> Any:
    """``check_value()`` on the engine: a ``ValueCheck``."""
    from starlayer.shacl.engine import value_check
    from starlayer.shacl.report_results import report_results
    from starlayer.shacl.value_check import ValueCheck

    data, shapes, _ont = _normalise(data_graph, shacl_graph if shacl_graph is not None else data_graph, None)
    conforming, report = value_check.check_value(
        data,
        shapes,
        property_shape,
        focus,
        value,
        subclass_of_in_shapes_graph=subclass_of_in_shapes_graph,
        conformance_disallows=conformance_disallows,
    )
    return ValueCheck(conforms=conforming, results=report_results(report))


def form_model(**options: Any) -> Any:
    """``form_model()`` on the engine: a ``FormModel`` (the options are those of ``starlayer.shacl.form_model`` plus the processor's)."""
    from starlayer.shacl.form_model import form_model as build

    return build(**options)


def extract_shapes_graph(shapes_graph: Any, shapes_graph_iri: Any, *, include_referenced: bool) -> Any:
    """``StarShaclProcessor.extract_shapes_graph`` on the engine."""
    from starlayer.shacl.engine.shapes_graphs import (
        extract_shapes_graph as engine_extract,
    )

    return engine_extract(shapes_graph, shapes_graph_iri, include_referenced=include_referenced)


def close_shape(shapes_graph: Any, shape: Any, *, imports_loader: Any = None, ignore_imports: bool | None = None) -> Any:
    """``StarShaclProcessor.close_shape`` on the engine."""
    from starlayer.shacl.engine.shapes_graphs import close_shape as engine_close

    return engine_close(shapes_graph, shape, imports_loader=imports_loader, ignore_imports=ignore_imports)
