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

from rdflib import URIRef

from starlayer.shacl_engine.plan import Term


@dataclass(frozen=True)
class Violation:
    value: Term = None  # sh:value; None means no sh:value is reported
    message: str | None = None
    path: Any = None  # a Path overriding the shape's own (used e.g. by closed, which reports the offending predicate)
    component: URIRef | None = None  # override when one function serves several components
    value_set: bool = True  # False: report no sh:value even if value is None-like


@dataclass(frozen=True)
class ComponentSpec:
    iri: URIRef
    predicates: tuple[URIRef, ...]
    fn: Callable[..., Iterable[Violation]]


REGISTRY: dict[URIRef, ComponentSpec] = {}


def component(iri: URIRef, *predicates: URIRef):
    def deco(fn):
        REGISTRY[iri] = ComponentSpec(iri, tuple(predicates), fn)
        return fn

    return deco


def all_param_predicates() -> set[URIRef]:
    return {p for spec in REGISTRY.values() for p in spec.predicates}
