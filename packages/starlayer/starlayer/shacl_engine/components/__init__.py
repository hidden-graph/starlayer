"""The SHACL constraint component implementations; importing the package imports each module that registers some.

Each module registers its components with the decorator in ``registry``, so the registry is populated as a side effect
of this import.
"""

from starlayer.shacl_engine.components import (  # noqa: F401
    core_cross_node,
    core_shape_based,
    core_string_pair,
    core_value,
    expression_components,
    registry,
    sparql_constraints,
)
