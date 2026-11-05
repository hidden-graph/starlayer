"""``ox_out``: the decorator behind the rule "an Oxigraph graph in -> an ``StarLayerGraph`` out".

A library function that runs on rdflib code and returns a graph (or a result holding graphs) is decorated with the names of its
graph parameters. When any of them is an ``StarLayerGraph`` / ``StarLayerDataset`` / ``pyoxigraph.Store`` the graphs in the result are
converted to ``StarLayerGraph`` (pyoxigraph terms; the prefixes of the inputs plus those the result's IRIs use); with any other input
the result is returned as it is. The conversion lives in ``starlayer.graph.oxgraph._rdflib_bridge``, imported at call time
because that package imports the modules that use this decorator.
"""

from __future__ import annotations

import functools
from collections.abc import Callable
from typing import Any


def ox_out(*graph_params: str, owner_sources: str | None = None) -> Callable:
    """See the module docstring. ``owner_sources`` names a dict attribute of ``self`` whose values are bound graphs (a method)."""

    def decorate(fn: Callable) -> Callable:
        wrapped: list[Callable] = []

        @functools.wraps(fn)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            if not wrapped:
                from starlayer.graph.oxgraph._rdflib_bridge import ox_in_ox_out

                wrapped.append(ox_in_ox_out(*graph_params, owner_sources=owner_sources)(fn))
            return wrapped[0](*args, **kwargs)

        return wrapper

    return decorate
