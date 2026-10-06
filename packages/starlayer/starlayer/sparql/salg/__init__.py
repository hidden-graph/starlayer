# The salg: vocabulary's own SHACL/RDFS validation and cross-referential
# semantic checks, broken out of the top-level starlayer.sparql namespace
# 2026-10-05 into their own submodule here - mirroring srl's own precedent
# (flattened into starlayer.sparql's top level 2026-10-03, reverted the same
# day: that made every name reachable by two different paths). Access as
# `from starlayer.sparql import salg` then `salg.ontology_graph(...)`/etc.
#
# query_to_rdf/rdf_to_query/update_to_rdf/rdf_to_update/queries_to_collection/
# rdf_to_collection/SALG deliberately stay at starlayer.sparql's own top
# level, not re-exported here too - they live in to_rdf.py/from_rdf.py/
# vocab.py, which are shared generic machinery reused directly by the ssyn:/
# sast:/srl: vocabularies as well (to_rdf._encode, from_rdf._decode,
# to_rdf._new_starlayer_graph, vocab.py's dirlang-encoding helpers), not
# salg:-exclusive - moving those files here would mean three unrelated
# vocabularies importing from a package named after a fourth one.
from .sparql_ontology import ontology_graph
from .semantic_checks import UnboundProjectedVariable, find_unbound_projected_variables

__all__ = [
    "ontology_graph",
    "find_unbound_projected_variables",
    "UnboundProjectedVariable",
]

try:
    from .sparql_shapes import shapes_graph, validate_query

    __all__ += ["shapes_graph", "validate_query"]
except ImportError:
    # pyshacl is a test/optional dependency - sparql_shapes.py is unusable
    # without it, but the rest of this submodule must still import fine.
    pass
