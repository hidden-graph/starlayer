# Must run before anything else in this package: grammar12.install() mutates
# rdflib's shared, global parser grammar objects in place (splicing in
# SPARQL 1.2 productions), and from_rdf.py's _discover_expr_evalfns() takes
# an import-time snapshot of that same grammar. If anything imports this
# package (pulling in from_rdf.py) before parse12/grammar12.install() has
# run, later queries can silently evaluate wrong (confirmed via a minimal,
# deterministic, non-pytest repro — not a guess) — install() is idempotent
# per its own docstring, so forcing it first here is safe regardless of
# whether a caller also imports parse12 directly later.
#
# rdflib is an optional extra, and this facade's names are rdflib-based (the SPARQL 1.2 parse/prepare machinery, salg trees,
# ``StarQuery``), while ``StarLayerGraph`` / ``StarLayerDataset`` reach into ``starlayer.sparql.*`` submodules for query support.
# So this package imports nothing eagerly; every public name is imported from its submodule on first access (PEP 562).
# The ordering rule above now lives in ``spexpr_codec.py`` (the module that snapshots the grammar), which imports ``parse12``
# first. Without rdflib, a name that needs it raises an ImportError naming the extra.
from __future__ import annotations

import importlib
from typing import Any

_LAZY = {
    "check_query": "check",
    "rdf_to_collection": "from_rdf",
    "rdf_to_query": "from_rdf",
    "rdf_to_update": "from_rdf",
    "prepare_query_12": "parse12",
    "prepare_update_12": "parse12",
    "StarQuery": "star_query",
    "queries_to_collection": "to_rdf",
    "query_to_rdf": "to_rdf",
    "update_to_rdf": "to_rdf",
    "SALG": "_vocab_rdflib",  # the rdflib namespace the salg encoder uses (the pyoxigraph SQE / SPEXPR are in sparql.vocab)
}


def __getattr__(name: str) -> Any:
    if name in _LAZY:
        value = getattr(importlib.import_module(f"{__name__}.{_LAZY[name]}"), name)
        globals()[name] = value
        return value
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


def __dir__() -> list[str]:
    return sorted(set(globals()) | set(_LAZY))

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

# SRL - deliberately NOT flattened into individual names here
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
    "check_query",
    "SALG",
    "StarQuery",
    "prepare_query_12",
    "prepare_update_12",
    "query_to_rdf",
    "rdf_to_query",
    "queries_to_collection",
    "rdf_to_collection",
    "update_to_rdf",
    "rdf_to_update",
]
