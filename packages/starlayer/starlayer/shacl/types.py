"""Runtime-checkable protocols for a graph with a namespace manager, and a mutable variant."""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable


@runtime_checkable
class StarLayerGraphProtocol(Protocol):
    """Structural protocol for a graph with a ``namespace_manager`` that can be iterated."""

    namespace_manager: Any

    def __iter__(self):
        """Iterates the graph's statements."""
        ...


@runtime_checkable
class MutableStarLayerGraphProtocol(StarLayerGraphProtocol, Protocol):
    """``StarLayerGraphProtocol`` plus mutation methods - ``add()``/
    ``remove()``.
    """

    def add(self, triple: tuple[Any, Any, Any]) -> Any:
        """Adds ``triple`` to the graph."""
        ...

    def remove(self, triple_pattern: tuple[Any, Any, Any]) -> Any:
        """Removes every triple matching ``triple_pattern`` from the
        graph.
        """
        ...
