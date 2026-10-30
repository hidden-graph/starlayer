"""Lazy trampolines for vocabulary-specific components that live outside the engine.

Each entry registers a component under its IRI and predicate without importing the owning package; the owner's module
is imported on the first call. This keeps the dependency pointing one way (owner -> engine) and avoids import cycles
and a new import-time dependency from the engine on, say, ``starlayer.sparql.salg``.
"""

from __future__ import annotations

from importlib import import_module

from rdflib import URIRef

from starlayer.shacl_engine.components.registry import component

_SALG = "https://github.com/hidden-graph/starlayer/ns/sparql/algebra#"


def _lazy(module: str, name: str):
    def call(ctx, shape, params, focus, values):
        return getattr(import_module(module), name)(ctx, shape, params, focus, values)

    return call


component(URIRef(_SALG + "NoUnboundProjectedVariablesConstraintComponent"), URIRef(_SALG + "noUnboundProjectedVariables"))(
    _lazy("starlayer.sparql.salg.engine_components", "no_unbound_projected_variables")
)
