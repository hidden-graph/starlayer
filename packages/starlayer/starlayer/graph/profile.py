"""``profile(graph)``: what a graph's data says about itself, in one pass.

Each class with its number of instances (the subjects of ``rdf:type`` triples whose object is an IRI), each property with its number of
triples, and for any set of nodes the properties they use: how many of the nodes have the property, the most values one node has, the
datatypes of its literal values and the kinds of value it has (``"iri"``, ``"blank"``, ``"literal"``, ``"triple"``). A profile is a snapshot:
it is not updated when the graph changes, so build another (the caller decides when; there is no cache here). A dataset is profiled as the union of
all its graphs (a triple that several graphs hold counts once), whatever ``default_union`` is, and ``profile.graphs`` has the profile of each graph.

``graph.profile()`` is the same. Terms are pyoxigraph terms.
"""

from __future__ import annotations

from typing import Any, NamedTuple

import pyoxigraph as ox

from starlayer.graph.terms import RDF_TYPE, term_kind


class PropertyUse(NamedTuple):
    """How a set of nodes uses one property."""

    property: Any  # the property's IRI
    nodes: int  # how many of the nodes have it
    max_values: int  # the most values one node has
    datatypes: frozenset  # the datatypes of the literal values (``rdf:langString`` for a language-tagged one)
    kinds: frozenset  # a subset of "iri", "blank", "literal", "triple"


class GraphProfile:
    """The profile of a graph: ``classes``, ``properties``, ``subjects``, ``instances(cls)``, ``types_of(node)``, ``class_properties(cls)``,
    ``properties_of(nodes)`` and ``graphs``."""

    def __init__(self, by_node: dict, types: dict, predicates: dict, graphs: dict | None = None) -> None:
        """Built by ``profile()``; ``by_node`` maps node -> {property: [triples, datatypes, kinds]}."""
        self._graphs = graphs if graphs is not None else {}
        self._by_node = by_node
        self._types = types
        self._predicates = predicates
        instances: dict = {}
        for node, kinds in types.items():
            for cls in kinds:
                instances.setdefault(cls, []).append(node)
        self._instances = instances

    @property
    def graphs(self) -> dict[Any, GraphProfile]:
        """``{graph name: the profile of that graph}`` for every graph of a dataset, the default graph (``DefaultGraph``) and empty named graphs
        included. For a graph, its own name and this profile."""
        return dict(self._graphs)

    @property
    def classes(self) -> dict[Any, int]:
        """``{class: number of instances}`` for the classes the graph has instances of (exactly that class, not its subclasses)."""
        return {cls: len(nodes) for cls, nodes in self._instances.items()}

    @property
    def properties(self) -> dict[Any, int]:
        """``{property: number of triples}`` for every predicate of the graph."""
        return dict(self._predicates)

    @property
    def subjects(self) -> frozenset:
        """Every subject of the graph (typed or not)."""
        return frozenset(self._by_node)

    def instances(self, cls: Any) -> list[Any]:
        """The nodes typed exactly ``cls``."""
        return list(self._instances.get(cls, ()))

    def types_of(self, node: Any) -> frozenset:
        """The IRIs ``node`` is typed with."""
        return frozenset(self._types.get(node, ()))

    def properties_of(self, nodes: Any) -> list[PropertyUse]:
        """The properties ``nodes`` use, most used first (then by IRI text)."""
        found: dict = {}
        for node in nodes:
            for p, (count, datatypes, kinds) in self._by_node.get(node, {}).items():
                use = found.setdefault(p, [0, 0, set(), set()])
                use[0] += 1
                use[1] = max(use[1], count)
                use[2] |= datatypes
                use[3] |= kinds
        return sorted((PropertyUse(p, n, m, frozenset(d), frozenset(k)) for p, (n, m, d, k) in found.items()), key=lambda u: (-u.nodes, u.property.value))

    def class_properties(self, cls: Any) -> list[PropertyUse]:
        """The properties the instances of ``cls`` use (see ``properties_of``)."""
        return self.properties_of(self._instances.get(cls, ()))


def _union(dataset: Any) -> Any:
    seen: set = set()
    for q in dataset.quads():
        key = (q.subject, q.predicate, q.object)
        if key not in seen:
            seen.add(key)
            yield key


def profile(graph: Any) -> GraphProfile:
    """Profile ``graph`` (a ``StarLayerGraph`` or ``StarLayerDataset``) in one pass over its triples; a dataset's graphs are profiled one by one as well."""
    from starlayer.graph.core import StarLayerDataset

    types: dict = {}
    by_node: dict = {}
    predicates: dict = {}
    for s, p, o in (_union(graph) if isinstance(graph, StarLayerDataset) else graph.triples()):
        predicates[p] = predicates.get(p, 0) + 1
        if p == RDF_TYPE and isinstance(o, ox.NamedNode):
            types.setdefault(s, set()).add(o)
        use = by_node.setdefault(s, {}).setdefault(p, [0, set(), set()])
        use[0] += 1
        kind = term_kind(o)
        use[2].add(kind)
        if kind == "literal":
            use[1].add(o.datatype)
    result = GraphProfile(by_node, types, predicates)
    if isinstance(graph, StarLayerDataset):
        names = [ox.DefaultGraph(), *sorted(graph.store.named_graphs(), key=str)]
        result._graphs = {name: profile(graph.graph(name)) for name in names}
    else:
        result._graphs = {graph.identifier: result}
    return result
