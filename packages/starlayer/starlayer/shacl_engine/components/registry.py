"""Constraint component registry. A component module registers one function per SHACL constraint component:

    @component(SH.MinCountConstraintComponent, SH.minCount)
    def min_count(ctx, shape, params, focus, values):
        ...yield Violation(value=..., message=...)

``params`` maps every parameter predicate the shape has (from this component's declared ``*predicates``) to its tuple
of values. The function is called once per (shape, focus node) when the shape has at least one of the declared
predicates; it yields ``Violation`` records. The executor adds focus node, severity, path, source shape and component.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable
from dataclasses import dataclass
from typing import Any

from starlayer.shacl_engine.plan import Term
from starlayer.shacl_engine.terms import NamedNode as URIRef
from starlayer.shacl_engine.terms import to_engine


@dataclass(frozen=True)
class Violation:
    value: Term = None  # sh:value; None means no sh:value is reported
    message: str | None = None
    path: Any = None  # a Path overriding the shape's own (used e.g. by closed, which reports the offending predicate)
    component: URIRef | None = None  # override when one function serves several components
    value_set: bool = True  # False: report no sh:value even if value is None-like
    source_constraint: Term = None  # sh:sourceConstraint (SPARQL-based constraints: the sh:sparql node)
    severity: Term = None  # overrides the shape's severity for this result (sh:severity on a sh:sparql node)
    messages: tuple[Any, ...] = ()  # RDF literals; take precedence over the shape's sh:message
    annotations: tuple[tuple[Any, Any], ...] = ()  # (property, value) pairs added to the result (sh:resultAnnotation)
    details: tuple[Any, ...] = ()  # nested ``executor.Result`` records, reported as sh:detail of this result


@dataclass(frozen=True)
class ComponentSpec:
    iri: URIRef
    predicates: tuple[URIRef, ...]
    fn: Callable[..., Iterable[Violation]]
    required: tuple[URIRef, ...] = ()  # when set, the component applies only if the shape has all of these (SPARQL-based
    # components: the non-optional parameters)


REGISTRY: dict[URIRef, ComponentSpec] = {}


def component(iri: URIRef, *predicates: URIRef):
    """Register ``fn`` under a component IRI. rdflib IRIs are accepted and converted (``to_engine``); ``fn`` itself then
    receives engine terms unless it was wrapped with ``extensions.legacy_adapter``."""

    def deco(fn):
        iri_ = to_engine(iri)
        REGISTRY[iri_] = ComponentSpec(iri_, tuple(to_engine(p) for p in predicates), fn)
        return fn

    return deco


def static_specs() -> list[ComponentSpec]:
    """The built-in components. A plan adds the SPARQL-based ones declared in its shapes graph (``Plan.components``)."""
    return list(REGISTRY.values())


def all_param_predicates() -> set[URIRef]:
    return {p for spec in REGISTRY.values() for p in spec.predicates}
