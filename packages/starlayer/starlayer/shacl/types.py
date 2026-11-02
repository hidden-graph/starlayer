from __future__ import annotations

from typing import Any, Protocol, runtime_checkable


@runtime_checkable
class StarLayerGraphProtocol(Protocol):
    """Structural protocol every graph-like input to this package must
    satisfy: a bound ``namespace_manager`` plus iterability over triples.
    """

    namespace_manager: Any

    def __iter__(self):
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
