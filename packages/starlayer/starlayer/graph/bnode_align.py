"""Pair the blank nodes of one graph with those of another, so that ``diff`` and the set operators can compare graphs that have blank nodes.

A blank node has no name of its own: its label means nothing outside its graph, and ``diff``, ``-``, ``&`` and ``^`` compare labels. Two parses
of one document, or two versions of a graph, share no blank node. ``align_blank_nodes(graph, to=reference)`` decides which blank node of
``graph`` corresponds to which of ``reference`` and returns a copy of ``graph`` that uses the reference's labels for the pairs, so that
``diff(reference, aligned)`` and ``reference - aligned`` compare them as the same.

How two blank nodes are paired, in this order:

1. **Exact.** The same content and the same context: both nodes have the same edges to the same IRIs and literals, in and out, and to blank
   nodes that have the same property in turn (colour refinement over both graphs together). A pair is ``"ambiguous"`` when several nodes
   share that description (identical siblings): they are interchangeable, so any pairing gives the same result. A change to one node changes
   the whole description of everything connected to it, so the nodes that are left are then paired when they are the only ones with the
   same neighbourhood out to ``r`` edges, for ``r`` from the widest down to 1; these pairs are reported as ``"approximate"``.
2. **Approximate.** What is left is paired when it overlaps: the shared edges as a fraction of the edges of the node that has more of them
   (an edge to a blank node counts as the same edge when the predicate is the same). The pair needs ``min_overlap`` of that, or at most
   ``max_changes`` edges that the larger node has and the other has not (a small node that loses one edge is a big fraction of itself), and,
   when both nodes are reached from an IRI or from an already paired node, at least one of those incoming edges in common: a node under
   another parent is another node. The best pairs are made first, and each pairing makes the next one possible (a changed node deep in a structure
   is paired once its parent is).
3. **Unmatched.** Everything else, which ``diff`` reports as removed and added.

No pairing hides a difference: the aligned graph is isomorphic to ``graph``, so ``diff(reference, aligned)`` is empty only when the two graphs
are isomorphic, and applying the delta to ``reference`` gives a graph isomorphic to ``graph``. A poor pairing only makes the delta larger than it
needs to be, and ``Alignment.pairs`` shows every pairing and its kind, so the ones that could be wrong can be checked.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any

import pyoxigraph as ox

__all__ = ["Alignment", "BlankNodePair", "align_blank_nodes"]


@dataclass(frozen=True)
class BlankNodePair:
    """A blank node of the graph, the blank node of the reference it was paired with (``None`` when ``kind`` is ``"unmatched"``), how it was paired
    (``"exact"``, ``"ambiguous"``, ``"approximate"`` or ``"unmatched"``) and, for a pair made by overlap, its overlap score and the number of edges of
    the larger node that the other lacks (``changes``)."""

    node: ox.BlankNode
    partner: ox.BlankNode | None
    kind: str
    score: float | None = None
    changes: int | None = None


@dataclass(frozen=True)
class Alignment:
    """``graph``: a copy of the aligned graph whose blank nodes carry the reference's labels where they were paired and fresh labels elsewhere.
    ``pairs``: one ``BlankNodePair`` for each blank node of the original graph."""

    graph: Any
    pairs: list[BlankNodePair] = field(default_factory=list)

    def of_kind(self, kind: str) -> list[BlankNodePair]:
        """The pairs of one kind: ``"exact"``, ``"ambiguous"``, ``"approximate"`` or ``"unmatched"``."""
        return [p for p in self.pairs if p.kind == kind]


def _is_blank(term: Any) -> bool:
    return isinstance(term, ox.BlankNode)


def _edges(triples: list[tuple[Any, Any, Any]], side: int) -> dict[tuple[int, Any], list[tuple[str, str, Any]]]:
    """For each blank node ``(side, label)``: its edges ``(direction, predicate, other)``, ``other`` a term string or a blank node ``(side, label)``."""
    edges: dict[tuple[int, Any], list[tuple[str, str, Any]]] = defaultdict(list)
    for s, p, o in triples:
        if _is_blank(s):
            edges[(side, s)].append(("out", str(p), (side, o) if _is_blank(o) else str(o)))
        if _is_blank(o):
            edges[(side, o)].append(("in", str(p), (side, s) if _is_blank(s) else str(s)))
    return edges


def _refine(edges: dict[tuple[int, Any], list[tuple[str, str, Any]]]) -> list[dict[tuple[int, Any], int]]:
    """Colour refinement of all the blank nodes of both graphs together, so that equal colours mean equal neighbourhoods across the graphs.
    The colours after each round, the last being the stable one: round ``r`` describes a node by everything within ``r`` edges of it."""
    colour = dict.fromkeys(edges, 0)
    rounds = [colour]
    classes = 1
    while True:
        intern: dict[Any, int] = {}
        new: dict[tuple[int, Any], int] = {}
        for node, es in edges.items():
            signature = (colour[node], tuple(sorted((d, p, ("c", colour[o]) if isinstance(o, tuple) else ("t", o)) for d, p, o in es)))
            new[node] = intern.setdefault(signature, len(intern))
        rounds.append(new)
        if len(intern) == classes:
            return rounds
        classes, colour = len(intern), new


def _anchored(edges: list[tuple[str, str, Any]], partner: dict[tuple[int, Any], Any]) -> set[tuple[str, str, Any]]:
    """The edges of a node as comparable keys: a term string, the label a paired neighbour stands for, or a wildcard for an unpaired blank node."""
    keys = set()
    for d, p, o in edges:
        keys.add((d, p, partner.get(o, "_") if isinstance(o, tuple) else o))
    return keys


def _is_resolved(key: tuple[str, str, Any]) -> bool:
    return key[2] != "_"


def _compare(a: set[tuple[str, str, Any]], b: set[tuple[str, str, Any]]) -> tuple[float, int] | None:
    """The shared edges as a fraction of the larger node's edges, and how many of the larger node's edges the other lacks; ``None`` for two
    nodes that cannot be the same node (no incoming edge in common, or nothing in common)."""
    anchors_a = {k for k in a if k[0] == "in" and _is_resolved(k)}
    anchors_b = {k for k in b if k[0] == "in" and _is_resolved(k)}
    if (anchors_a or anchors_b) and not (anchors_a & anchors_b):
        return None  # reached from somewhere else, or from nowhere the other is reached from: another node
    shared, larger = len(a & b), max(len(a), len(b))
    return (shared / larger, larger - shared) if shared else None


def _match(old: list[tuple[Any, Any, Any]], new: list[tuple[Any, Any, Any]], min_overlap: float, max_changes: int) -> dict[ox.BlankNode, BlankNodePair]:
    edges_old, edges_new = _edges(old, 0), _edges(new, 1)
    rounds = _refine({**edges_old, **edges_new})
    result: dict[ox.BlankNode, BlankNodePair] = {}
    to_old: dict[tuple[int, Any], Any] = {}  # a paired new node -> the label of its partner
    own_old: dict[tuple[int, Any], Any] = {}  # an old node that has a partner -> its own label

    # 1. exact: equal colours once the refinement is stable; then, from the widest neighbourhood down, nodes that are the only ones left with
    #    the same neighbourhood out to ``r`` edges. A change to a node changes the stable colour of everything connected to it, but not the
    #    narrower neighbourhoods of the nodes far from it.
    for r in range(len(rounds) - 1, 0, -1):
        colour = rounds[r]
        by_colour: dict[int, tuple[list[Any], list[Any]]] = defaultdict(lambda: ([], []))
        for (side, label), c in colour.items():
            if (side, label) in own_old or (side == 1 and label in result):
                continue
            by_colour[c][side].append(label)
        for olds, news in by_colour.values():
            olds.sort(key=str)
            news.sort(key=str)
            unique = len(olds) == 1 and len(news) == 1
            if r < len(rounds) - 1 and not unique:
                continue
            kind = "exact" if r == len(rounds) - 1 and unique else ("ambiguous" if r == len(rounds) - 1 else "approximate")
            for o, n in zip(olds, news, strict=False):
                result[n] = BlankNodePair(n, o, kind, None if kind != "approximate" else round(float(r) / (len(rounds) - 1), 3))
                to_old[(1, n)] = o
                own_old[(0, o)] = o

    # 2. approximate: overlap, best first, repeated while a pairing makes another possible
    while True:
        free_old = [n for n in edges_old if n not in own_old]
        free_new = [n for n in edges_new if n[1] not in result]
        if not free_old or not free_new:
            break
        keys_old = {n: _anchored(edges_old[n], {k: v for k, v in own_old.items()}) for n in free_old}
        keys_new = {n: _anchored(edges_new[n], to_old) for n in free_new}
        index: dict[tuple[str, str, Any], list[tuple[int, Any]]] = defaultdict(list)
        for n, ks in keys_old.items():
            for k in ks:
                if _is_resolved(k):
                    index[k].append(n)
        scored = []
        for n, ks in keys_new.items():
            candidates = {o for k in ks if _is_resolved(k) for o in index.get(k, [])}
            for o in candidates:
                compared = _compare(ks, keys_old[o])
                if compared is not None and (compared[0] >= min_overlap or compared[1] <= max_changes):
                    scored.append((-compared[0], compared[1], str(n[1]), str(o[1]), n, o))
        if not scored:
            break
        scored.sort(key=lambda t: t[:4])
        taken_new: set[Any] = set()
        taken_old: set[Any] = set()
        for neg, changes, _, _, n, o in scored:
            if n in taken_new or o in taken_old:
                continue
            taken_new.add(n)
            taken_old.add(o)
            result[n[1]] = BlankNodePair(n[1], o[1], "approximate", round(-neg, 3), changes)
            to_old[n] = o[1]
            own_old[o] = o[1]

    for n in edges_new:
        result.setdefault(n[1], BlankNodePair(n[1], None, "unmatched"))
    return result


def align_blank_nodes(graph: Any, to: Any, *, min_overlap: float = 0.5, max_changes: int = 1) -> Alignment:
    """``graph`` with its blank nodes relabelled to match the blank nodes of ``to``, and the pairing that did it; see the module docstring.

    ``min_overlap`` (0 to 1) is how much two blank nodes that are not exactly alike must have in common to be treated as the same node: the
    shared edges as a fraction of the edges of the node that has more of them. 1 pairs only nodes that are alike except for an unpaired
    neighbour, and a lower value pairs more of the nodes that were edited. ``max_changes`` is how many of the larger node's edges the other may
    lack, whatever the fraction: a node with three edges that loses one is 0.67 of itself, which a ``min_overlap`` of 0.75 would refuse, and
    ``max_changes=1`` still pairs. ``max_changes=0`` leaves it to ``min_overlap``. Nodes that are exactly alike are always paired.

    ``graph`` and ``to`` are ``StarLayerGraph`` objects. The result's ``graph`` is a new ``StarLayerGraph`` with the prefixes of ``graph``. A blank
    node inside a triple term is handled through the RDF 1.1 basic encoding.

    Raises:
        TypeError: a dataset or another kind of object.
        ValueError: ``min_overlap`` outside 0 to 1, or a negative ``max_changes``.
    """
    from starlayer.graph import interop
    from starlayer.graph.core import StarLayerGraph

    if not isinstance(graph, StarLayerGraph) or not isinstance(to, StarLayerGraph):
        raise TypeError("align_blank_nodes takes two StarLayerGraph objects")
    if not 0 <= min_overlap <= 1:
        raise ValueError("min_overlap must be between 0 and 1")
    if max_changes < 0:
        raise ValueError("max_changes must not be negative")
    new = list(graph.triples((None, None, None)))
    old = list(to.triples((None, None, None)))
    encode = any(isinstance(t[2], ox.Triple) or isinstance(t[0], ox.Triple) for t in new + old)
    if encode:
        new_quads = interop.to_basic([ox.Quad(s, p, o, ox.DefaultGraph()) for s, p, o in new])
        old_quads = interop.to_basic([ox.Quad(s, p, o, ox.DefaultGraph()) for s, p, o in old])
        new = [(q.subject, q.predicate, q.object) for q in new_quads]
        old = [(q.subject, q.predicate, q.object) for q in old_quads]
    pairs = _match(old, new, min_overlap, max_changes)
    label = {n: (p.partner if p.partner is not None else ox.BlankNode()) for n, p in pairs.items()}

    def relabel(term: Any) -> Any:
        return label[term] if _is_blank(term) else term

    relabelled = [(relabel(s), p, relabel(o)) for s, p, o in new]
    if encode:
        restored = interop.from_basic([ox.Quad(s, p, o, ox.DefaultGraph()) for s, p, o in relabelled])
        relabelled = [(q.subject, q.predicate, q.object) for q in restored]
    aligned = StarLayerGraph(prefixes=dict(graph.prefixes))
    aligned.extend(relabelled)
    original = {n for t in graph.triples((None, None, None)) for n in (t[0], t[2]) if _is_blank(n)}
    return Alignment(aligned, [p for n, p in sorted(pairs.items(), key=lambda kv: str(kv[0])) if n in original])
