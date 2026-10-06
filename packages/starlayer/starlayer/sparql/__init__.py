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
from .parse12 import prepare_query_12, prepare_update_12
from .to_rdf import queries_to_collection, query_to_rdf, update_to_rdf
from .vocab import SALG

# salg: itself (ontology_graph/shapes_graph/validate_query/
# find_unbound_projected_variables/UnboundProjectedVariable) - broken out
# into its own submodule 2026-10-05, same reasoning as the SRL note below:
# `from starlayer.sparql import salg` then `salg.ontology_graph(...)`/etc,
# not flattened here. query_to_rdf/rdf_to_query/update_to_rdf/rdf_to_update/
# queries_to_collection/rdf_to_collection/SALG above stay flat though - they
# live in to_rdf.py/from_rdf.py/vocab.py, shared generic machinery the
# ssyn:/sast:/srl: vocabularies also depend on directly, not salg:-exclusive
# files - moving those would mean three unrelated vocabularies importing
# from a package named after a fourth one. See `salg/__init__.py`'s own
# comment for the full account.

# SRL/SPARQL-RL - deliberately NOT flattened into individual names here
# (tried 2026-10-03, reverted same day) - that would mean every one of
# `srl.py`/`srl_eval.py`'s own names is reachable by two different paths
# (`starlayer.sparql.X` and `starlayer.sparql.srl.X`), the exact anti-
# pattern already removed elsewhere in this codebase (`starlayer.registry`,
# `ontology_graph()`/`shapes_graph()` wrappers, `get_ontology_turtle12()`).
# The one real path is the submodule itself - `from starlayer.sparql
# import srl` (ordinary Python package traversal, nothing to maintain
# here) - then `srl.parse_ruleset(...)`/`srl.srl_validate(...)`/
# `srl.RuleSet`/etc (the AST dataclasses - `RuleSet`/`Rule`/`Data`/
# `TriplePattern`/`FilterElement`/`AssignmentElement`/`NegationElement` -
# are re-exported from `srl.py` too, 2026-10-05; their own home,
# `_srl_ast.py`, is private and not directly importable - same one-real-
# path reasoning), or `from starlayer.sparql import srl_eval`/
# `srl_semantic_checks` for the sibling pieces. This is also why `srl.py`'s own
# `srl_`-prefixed names (`srl_parse_to_tree`/`srl_tree_to_text`/
# `srl_validate`) stay prefixed even without a flat re-export to collide
# through - a caller who also does `from starlayer.starontology.manchester
# import manchester_parse_to_tree` and separately imports this module's
# bare `parse_to_tree` would still hit the same collision at that call site.

__all__ = [
    "SALG",
    "prepare_query_12",
    "prepare_update_12",
    "query_to_rdf",
    "rdf_to_query",
    "queries_to_collection",
    "rdf_to_collection",
    "update_to_rdf",
    "rdf_to_update",
]
