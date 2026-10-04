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
from .from_rdf import rdf_to_collection, rdf_to_query, rdf_to_update
from .sparql_ontology import ontology_graph
from .parse12 import prepare_query_12, prepare_update_12
from .semantic_checks import UnboundProjectedVariable, find_unbound_projected_variables
from .serialize12 import translate_algebra_12
from .to_rdf import queries_to_collection, query_to_rdf, update_to_rdf
from .vocab import SALG

# SRL/SPARQL-RL - deliberately NOT flattened into individual names here
# (tried 2026-10-03, reverted same day) - that would mean every one of
# `srl.py`/`srl_ast.py`/`srl_eval.py`'s own names is reachable by two
# different paths (`starlayer.sparql.X` and `starlayer.sparql.srl.X`),
# the exact anti-pattern already removed elsewhere in this codebase
# (`starlayer.registry`, `ontology_graph()`/`shapes_graph()` wrappers,
# `get_ontology_turtle12()`). The one real path is the submodule itself -
# `from starlayer.sparql import srl` (ordinary Python package traversal,
# nothing to maintain here) - then `srl.parse_ruleset(...)`/
# `srl.srl_validate(...)`/etc, or `from starlayer.sparql import srl_ast`/
# `srl_eval` for the sibling pieces. This is also why `srl.py`'s own
# `srl_`-prefixed names (`srl_parse_to_tree`/`srl_tree_to_text`/
# `srl_validate`) stay prefixed even without a flat re-export to collide
# through - a caller who also does `from starlayer.starontology.manchester
# import manchester_parse_to_tree` and separately imports this module's
# bare `parse_to_tree` would still hit the same collision at that call site.

__all__ = [
    "SALG",
    "prepare_query_12",
    "prepare_update_12",
    "translate_algebra_12",
    "query_to_rdf",
    "rdf_to_query",
    "queries_to_collection",
    "rdf_to_collection",
    "update_to_rdf",
    "rdf_to_update",
    "ontology_graph",
    "find_unbound_projected_variables",
    "UnboundProjectedVariable",
]

try:
    from .sparql_shapes import shapes_graph, validate_query

    __all__ += ["shapes_graph", "validate_query"]
except ImportError:
    # pyshacl is a test/optional dependency - sparql_shapes.py is unusable
    # without it, but the rest of the package must still import fine.
    pass
