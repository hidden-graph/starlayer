"""A real pySHACL ``ConstraintComponent`` for the one cross-referential
semantic check this project's own SHACL shapes couldn't otherwise see: a
``salg:Project`` node's own ``salg:PV`` naming a variable never actually
bound anywhere in its own ``salg:p`` pattern subtree (see
``starlayer.sparql/semantic_checks.py``'s own module docstring for the full
design rationale - reusing rdflib's real ``_addVars`` bookkeeping rather
than reimplementing SPARQL's variable-scoping rules as a declarative
``sh:sparql`` query).

**Lives here, not in ``starlayer.shacl/native_components.py``.** That module is
generic SHACL 1.2 Core machinery with no knowledge of any one vocabulary;
this constraint is inherently ``salg:``-specific (it only makes sense for
a ``salg:Project`` node, and its activation predicate lives in the
``salg:`` namespace) - registering it from `starlayer.shacl` would mean that
package needing to know about `starlayer.sparql`'s own vocabulary, the wrong
direction for the dependency this project already has (`starlayer.sparql`
already depends on `starlayer.shacl`, not the reverse). Mirrors
`starlayer.shacl.native_components`'s own registration mechanism and
`SingleLineConstraintComponent`'s own boolean-marker-parameter pattern
exactly, just scoped to this package's own predicate.

Activated by ``salg:noUnboundProjectedVariables true`` on a ``sh:NodeShape``
(``salg:ProjectShape`` in ``sparql_shapes.ttl`` carries it) - the same
"boolean marker predicate opts a shape into a native check" convention
``sh:singleLine`` already established.
"""

from __future__ import annotations

from typing import Any

from rdflib import XSD, Literal
from rdflib.namespace import RDF

from .semantic_checks import _unbound_projected_variables_for_node
from .vocab import SALG

_registered = False


def register_salg_native_components() -> None:
    """Register this module's native constraint component into pySHACL's
    own dispatch map (idempotent - safe to call many times, only registers
    once per process). Mutates the same shared registry
    ``starlayer.shacl.native_components.register_native_components`` mutates -
    see that function's own docstring for why in-place mutation, not
    reassignment, is required."""
    global _registered
    if _registered:
        return

    from pyshacl.constraints import (
        ALL_CONSTRAINT_COMPONENTS,
        ALL_CONSTRAINT_PARAMETERS,
        CONSTRAINT_PARAMETERS_MAP,
    )

    CONSTRAINT_PARAMETERS_MAP[SALG.noUnboundProjectedVariables] = _NoUnboundProjectedVariablesConstraintComponent
    if SALG.noUnboundProjectedVariables not in ALL_CONSTRAINT_PARAMETERS:
        ALL_CONSTRAINT_PARAMETERS.append(SALG.noUnboundProjectedVariables)
    if _NoUnboundProjectedVariablesConstraintComponent not in ALL_CONSTRAINT_COMPONENTS:
        ALL_CONSTRAINT_COMPONENTS.append(_NoUnboundProjectedVariablesConstraintComponent)

    _registered = True


def _build_no_unbound_projected_variables_component() -> Any:
    from pyshacl.constraints.constraint_component import ConstraintComponent

    class NoUnboundProjectedVariablesConstraintComponent(ConstraintComponent):  # type: ignore[misc]
        """``salg:noUnboundProjectedVariables``: on a ``salg:Project``
        focus node, every variable in its own ``salg:PV`` must actually be
        bound somewhere in its own ``salg:p`` pattern subtree."""

        shacl_constraint_component = SALG.NoUnboundProjectedVariablesConstraintComponent
        shape_expecting = False
        list_taking = False

        def __init__(self, shape: Any) -> None:
            super().__init__(shape)
            value = next(iter(shape.sg.objects(shape.node, SALG.noUnboundProjectedVariables)))
            # Exact-term comparison against "true"^^xsd:boolean, not
            # bool(value.value) - see SingleLineConstraintComponent's
            # identical, deliberately-documented fix in
            # starlayer.shacl/native_components.py for why (a string literal
            # like "false" is still Python-truthy).
            if not (isinstance(value, Literal) and value.datatype == XSD.boolean):
                raise ValueError(
                    f"salg:noUnboundProjectedVariables on '{shape.node}' must be a "
                    f"xsd:boolean literal, got {value!r}."
                )
            self.enabled = str(value) == "true"

        @classmethod
        def constraint_parameters(cls) -> list[Any]:
            return [SALG.noUnboundProjectedVariables]

        @classmethod
        def constraint_name(cls) -> str:
            return "NoUnboundProjectedVariablesConstraintComponent"

        def evaluate(
            self,
            executor: Any,
            target_graph: Any,
            focus_value_nodes: dict[Any, Any],
            _evaluation_path: list[Any],
        ) -> tuple[bool, list[Any]]:
            reports: list[Any] = []
            non_conformant = False
            if not self.enabled:
                return True, reports
            for focus_node, value_nodes in focus_value_nodes.items():
                if (focus_node, RDF.type, SALG.Project) not in target_graph:
                    continue
                for issue in _unbound_projected_variables_for_node(focus_node, target_graph):
                    non_conformant = True
                    reports.append(
                        self.make_v_result(
                            target_graph,
                            focus_node,
                            value_node=issue.variable,
                            extra_messages=[
                                Literal(
                                    f"Projected variable {issue.variable.n3()} is never bound "
                                    f"anywhere in this Project node's own pattern (salg:p)."
                                )
                            ],
                        )
                    )
            return (not non_conformant), reports

    return NoUnboundProjectedVariablesConstraintComponent


_NoUnboundProjectedVariablesConstraintComponent = _build_no_unbound_projected_variables_component()
