"""Engine-side (``starlayer.shacl_engine``) twin of ``native_components.py``: ``salg:noUnboundProjectedVariables``.

The query analysis is the same pure function the pySHACL component uses
(``semantic_checks._unbound_projected_variables_for_node``); only the thin adapter differs. Dependency direction:
this module imports the engine registry, never the reverse. The engine reaches it through the trampoline in
``starlayer.shacl_engine.components.extensions``, which imports this module on first use, so neither the engine nor
the SPARQL algebra core packages (srl/sqe/spexpr) import salg at module import time. ``register()`` installs the
real function explicitly (idempotent).
"""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any

from rdflib import XSD, Graph, Literal
from rdflib.namespace import RDF

from starlayer.shacl_engine.components.registry import Violation, component
from starlayer.shacl_engine.plan import ShapeError

from ..vocab import SALG
from .semantic_checks import _unbound_projected_variables_for_node


def _as_graph(data: Any) -> Graph:
    """The semantic check needs ``Graph.value``; an entailed or native view is copied into a plain graph."""
    if isinstance(data, Graph):
        return data
    g = Graph()
    for t in data.triples((None, None, None)):
        g.add(t)
    return g


def no_unbound_projected_variables(ctx, shape, params, focus, values) -> Iterator[Violation]:
    for param in params[SALG.noUnboundProjectedVariables]:
        if not (isinstance(param, Literal) and param.datatype == XSD.boolean):
            raise ShapeError(f"salg:noUnboundProjectedVariables on '{shape.node}' must be a xsd:boolean literal, got {param!r}.")
        if str(param) != "true":
            continue
        if (focus, RDF.type, SALG.Project) not in ctx.data:
            continue
        for issue in _unbound_projected_variables_for_node(focus, _as_graph(ctx.data)):
            yield Violation(
                value=issue.variable,
                message=f"Projected variable {issue.variable.n3()} is never bound anywhere in this Project node's own pattern (salg:p).",
            )


def register() -> None:
    from starlayer.shacl_engine.components.extensions import legacy_adapter

    # the engine's terms are pyoxigraph terms; this module speaks rdflib terms, so register it behind the adapter
    component(SALG.NoUnboundProjectedVariablesConstraintComponent, SALG.noUnboundProjectedVariables)(
        legacy_adapter(lambda: no_unbound_projected_variables)
    )
