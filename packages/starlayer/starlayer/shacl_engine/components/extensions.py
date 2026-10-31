"""Lazy trampolines for vocabulary-specific components that live outside the engine.

Each entry registers a component under its IRI and predicate without importing the owning package; the owner's module
is imported on the first call. This keeps the dependency pointing one way (owner -> engine) and avoids import cycles
and a new import-time dependency from the engine on, say, ``starlayer.sparql.salg``.

Owners still speak rdflib terms, so the trampoline is a term-model boundary: it hands the owner rdflib-term views of the
data and shapes graphs (``LegacyTermView``), the parameters and focus node converted with ``from_engine``, and converts
the yielded violations back with ``to_engine``.
"""

from __future__ import annotations

from dataclasses import replace
from importlib import import_module
from types import SimpleNamespace

from starlayer.shacl_engine.components.registry import Violation, component
from starlayer.shacl_engine.terms import LegacyTermView, from_engine, to_engine
from starlayer.shacl_engine.terms import NamedNode as URIRef

_SALG = "https://github.com/hidden-graph/starlayer/ns/sparql/algebra#"


def _lazy(module: str, name: str):
    def call(ctx, shape, params, focus, values):
        fn = getattr(import_module(module), name)
        legacy_ctx = SimpleNamespace(
            data=LegacyTermView(ctx.data), shapes=LegacyTermView(ctx.shapes), plan=ctx.plan, cache=ctx.cache
        )
        legacy_params = {from_engine(k): tuple(from_engine(v) for v in vs) for k, vs in params.items()}
        legacy_shape = SimpleNamespace(**{**vars(shape), "node": from_engine(shape.node)})
        for v in fn(legacy_ctx, legacy_shape, legacy_params, from_engine(focus), tuple(from_engine(v) for v in values)):
            yield replace(v, value=to_engine(v.value)) if isinstance(v, Violation) else v

    return call


component(URIRef(_SALG + "NoUnboundProjectedVariablesConstraintComponent"), URIRef(_SALG + "noUnboundProjectedVariables"))(
    _lazy("starlayer.sparql.salg.engine_components", "no_unbound_projected_variables")
)
