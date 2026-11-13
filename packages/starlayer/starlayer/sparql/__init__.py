"""SPARQL 1.2 query checking, query-as-RDF trees, SPARQL Rules and relevant-subgraph extraction.

The public names (`check_query`, `StarQuery`, `relevant_subgraph`) load lazily from their submodules.
`srl`, `srl_eval` and `sqe` are reached as submodules (`from starlayer.sparql import srl`), not flattened here.
"""
# This package imports nothing eagerly; every public name is imported from its submodule on first access (PEP 562).
from __future__ import annotations

import importlib
from typing import Any

_LAZY = {
    "check_query": "check",
    "StarQuery": "star_query",
    "relevant_subgraph": "relevant",
}


def __getattr__(name: str) -> Any:
    """Import a public name from its submodule on first access and cache it in the module namespace."""
    if name in _LAZY:
        value = getattr(importlib.import_module(f"{__name__}.{_LAZY[name]}"), name)
        globals()[name] = value
        return value
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


def __dir__() -> list[str]:
    """List the module's names, including the lazy public names not yet imported."""
    return sorted(set(globals()) | set(_LAZY))

# SRL - deliberately NOT flattened into individual names here
# (tried 2026-10-03, reverted same day) - that would mean every one of
# `srl.py`/`srl_eval.py`'s own names is reachable by two different paths
# (`starlayer.sparql.X` and `starlayer.sparql.srl.X`), the exact anti-
# pattern already removed elsewhere in this codebase (a registry module,
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
    "StarQuery",
    "relevant_subgraph",
]
