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


def is_triple_term_like(value: Any) -> bool:
    return (
        hasattr(value, "subject")
        and hasattr(value, "predicate")
        and hasattr(value, "object")
    )


def is_dirlangstring_like(value: Any) -> bool:
    """Duck-typed check for starlayer.graph's ``DirLangString`` (RDF 1.2
    direction-tagged language string) without a hard import - no rdflib term
    has a ``.direction`` attribute, so this is a safe, specific discriminator.
    """
    return (
        hasattr(value, "value")
        and hasattr(value, "language")
        and hasattr(value, "direction")
    )


def ensure_graph_iterable(value: Any, *, name: str) -> None:
    if not is_starlayer_graph_like(value):
        raise TypeError(
            f"{name} must be a StarLayerGraph. "
            f"Got {type(value).__name__}."
        )


def ensure_graph_mutable(value: Any, *, name: str) -> None:
    ensure_graph_iterable(value, name=name)
    missing = [method for method in ("add", "remove") if not hasattr(value, method)]
    if missing:
        raise TypeError(
            f"{name} must support mutable graph operations {missing}. "
            f"Got {type(value).__name__}."
        )


def is_starlayer_graph_like(value: Any) -> bool:
    return hasattr(value, "namespace_manager") and hasattr(value, "__iter__")


def is_mutable_starlayer_graph_like(value: Any) -> bool:
    return is_starlayer_graph_like(value) and hasattr(value, "add") and hasattr(value, "remove")
