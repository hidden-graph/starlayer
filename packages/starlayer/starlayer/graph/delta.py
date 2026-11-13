"""``GraphDelta``: a set of triples to add and a set to remove, the difference between two graphs or a change to make.

``diff(old, new)`` is the delta that turns ``old`` into ``new``; ``delta.apply(graph)`` makes the change, ``delta.inverse()`` undoes
it and ``a.then(b)`` is the net effect of ``a`` followed by ``b``. Triples are compared as they are written, so a blank node is the
same node when it has the same label: use ``starlayer.graph.isomorphic`` to ask whether two graphs are the same up to blank node
names. A dataset is compared by its triples (the union of its graphs when ``default_union``).
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, field
from typing import Any

from starlayer.graph import terms

Triple = tuple[Any, Any, Any]


def _triples(items: Iterable[Any]) -> frozenset[Triple]:
    return frozenset((terms.term(s), terms.term(p), terms.term(o)) for s, p, o in items)


@dataclass(frozen=True)
class GraphDelta:
    """``added`` and ``removed`` triples. A delta that is not empty is true; the two sets do not overlap."""

    added: frozenset[Triple] = field(default_factory=frozenset)
    removed: frozenset[Triple] = field(default_factory=frozenset)

    def __post_init__(self) -> None:
        """Normalise the sets to term triples; a triple in both is no change and is dropped from both."""
        added, removed = _triples(self.added), _triples(self.removed)
        both = added & removed
        object.__setattr__(self, "added", added - both)
        object.__setattr__(self, "removed", removed - both)

    def __bool__(self) -> bool:
        """True when there is something to add or remove."""
        return bool(self.added or self.removed)

    def __len__(self) -> int:
        """The number of triples added and removed."""
        return len(self.added) + len(self.removed)

    def inverse(self) -> GraphDelta:
        """The delta that undoes this one: what was added is removed and what was removed is added."""
        return GraphDelta(added=self.removed, removed=self.added)

    def then(self, other: GraphDelta) -> GraphDelta:
        """The net effect of this delta followed by ``other`` (a triple added and then removed, or removed and then added, is no change)."""
        return GraphDelta(added=(self.added - other.removed) | (other.added - self.removed),
                          removed=(self.removed - other.added) | (other.removed - self.added))

    def apply(self, graph: Any) -> Any:
        """Remove ``removed`` from ``graph`` and add ``added``; returns ``graph``."""
        for triple in self.removed:
            graph.remove(triple)
        graph.extend(self.added)
        return graph

    def applied_to(self, graph: Any) -> frozenset[Triple]:
        """The triples ``graph`` would hold after ``apply``, without changing it."""
        return (frozenset(graph.triples()) - self.removed) | self.added


def diff(old: Any, new: Any) -> GraphDelta:
    """The delta that turns ``old`` into ``new``: the triples only ``new`` has are added, the triples only ``old`` has are removed."""
    before, after = frozenset(old.triples()), frozenset(new.triples())
    return GraphDelta(added=after - before, removed=before - after)
