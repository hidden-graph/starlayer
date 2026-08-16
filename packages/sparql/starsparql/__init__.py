# Must run before anything else in this package: grammar12.install() mutates
# rdflib's shared, global parser grammar objects in place (splicing in
# SPARQL 1.2 productions), and from_rdf.py's _discover_expr_evalfns() takes
# an import-time snapshot of that same grammar. If anything imports this
# package (pulling in from_rdf.py) before parse12/grammar12.install() has
# run, later queries can silently evaluate wrong (confirmed via a minimal,
# deterministic, non-pytest repro — not a guess) — install() is idempotent
# per its own docstring, so forcing it first here is safe regardless of
# whether a caller also imports parse12 directly later.
from . import parse12 as _parse12  # noqa: F401

from .vocab import SALG
from .to_rdf import query_to_rdf, queries_to_collection, update_to_rdf
from .from_rdf import rdf_to_query, rdf_to_collection, rdf_to_update
from .ontology import ontology_graph

__all__ = [
    "SALG",
    "query_to_rdf",
    "rdf_to_query",
    "queries_to_collection",
    "rdf_to_collection",
    "update_to_rdf",
    "rdf_to_update",
    "ontology_graph",
]

try:
    from .ontology.sparql_shapes import shapes_graph, validate

    __all__ += ["shapes_graph", "validate"]
except ImportError:
    # pyshacl is a test/optional dependency - sparql_shapes.py is unusable
    # without it, but the rest of the package must still import fine.
    pass
