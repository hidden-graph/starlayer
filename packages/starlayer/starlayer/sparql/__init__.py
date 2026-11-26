"""SPARQL 1.2 query checking, query-as-RDF trees, SPARQL Rules and relevant-subgraph extraction.

The public names (`check_query`, `QueryCheck`, `QueryProblem`, `StarQuery`, and the syntax-tree functions `sparql_to_tree`,
`tree_to_sparql` and `validate_sparql_tree`, which cover SPARQL queries, SPARQL Update and SRL rule sets) load lazily from their submodules.
`srl`, `srl_eval` and `sqe` are reached as submodules (`from starlayer.sparql import srl`), not flattened here.
"""
# This package imports nothing eagerly; every public name is imported from its submodule on first access (PEP 562).
from __future__ import annotations

import importlib
from typing import Any

_LAZY = {
    "check_query": "check",
    "QueryCheck": "check",
    "QueryProblem": "check",
    "StarQuery": "star_query",
    "sparql_to_tree": "syntax_tree",
    "tree_to_sparql": "syntax_tree",
    "validate_sparql_tree": "syntax_tree",
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

# SRL is deliberately NOT flattened into individual names here: `srl.py`'s own names (`parse_ruleset`, `RuleSet`, `ruleset_to_tree`,
# ...) are reached as `from starlayer.sparql import srl`, one real path. The text-to-tree, tree-to-text and validation
# functions are the exception, because they cover SPARQL, Update and SRL alike: `sparql_to_tree`, `tree_to_sparql`,
# `validate_sparql_tree` (`syntax_tree.py`).

__all__ = [
    "check_query",
    "QueryCheck",
    "QueryProblem",
    "StarQuery",
    "sparql_to_tree",
    "tree_to_sparql",
    "validate_sparql_tree",
]
