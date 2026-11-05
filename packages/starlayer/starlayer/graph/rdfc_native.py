"""Isomorphism and canonical forms over pyoxigraph, using Oxigraph's native RDFC-1.0.

* :func:`isomorphic` canonicalises both datasets natively and compares. Oxigraph's canonicaliser accepts
  triple terms (blank nodes inside them are relabelled consistently), but no specification defines the
  canonical labels of triple terms, so that output must not be compared with another implementation's.
* :func:`canonical_quads`, :func:`canonical_nquads` and :func:`canonical_hash` apply the Interoperability
  draft's basic encoding (:func:`starlayer.graph.interop.to_basic`) first, then RDFC-1.0, so the result
  is RDFC-1.0 of an RDF 1.1-shaped dataset and rests on a documented rewriting. The form is defined by
  that draft and may change with it. RDFC-1.0 has no triple-term rule of its own.

Dataset poisoning (RDFC-1.0 section 7.1, the W3C poison test074): Oxigraph's canonicaliser has no denial-of-service defence,
and a highly symmetric dataset (a clique of 10 blank nodes, a 6 x 6 torus of blank nodes) does not finish. Before every
canonicalisation :func:`check_complexity` runs a cheap colour refinement and raises
:class:`CanonicalizationComplexityError` for such a structure. It is a heuristic, not a proof of termination (see its docstring).
"""

from __future__ import annotations

import hashlib

import pyoxigraph as ox

from starlayer.graph.interop import to_basic

__all__ = ["isomorphic", "canonical_quads", "canonical_nquads", "canonical_hash", "check_complexity", "CanonicalizationComplexityError"]

# The largest cyclomatic number (edges - nodes + 1) that a connected group of mutually indistinguishable blank nodes may have.
# Measured on pyoxigraph 0.5.13 (RDFC-1.0 time): a 7-blank-node clique (15) 1.3 s, a 5 x 5 complete bipartite graph (16) 3 s,
# a 4 x 4 torus (17) 0.2 s, a 200-node cycle (1) 1.4 s; an 8-clique (21) 13 s, K(6,6) (25) and a 6 x 6 torus (37) do not finish.
MAX_SYMMETRIC_CYCLE_RANK = 20


class CanonicalizationComplexityError(RuntimeError):
    """The dataset has a highly symmetric blank-node structure that RDFC-1.0 would take exponential time on (RDFC-1.0
    section 7.1, "Dataset Poisoning": implementations MUST terminate early with an exception)."""

_ALGORITHMS = {
    "sha256": ox.CanonicalizationAlgorithm.RDFC_1_0,
    "sha384": ox.CanonicalizationAlgorithm.RDFC_1_0_SHA_384,
}
_HASHES = {"sha256": hashlib.sha256, "sha384": hashlib.sha384}


def _quads(data) -> list[ox.Quad]:
    out = []
    for item in data:
        if isinstance(item, ox.Triple):
            item = ox.Quad(item.subject, item.predicate, item.object, ox.DefaultGraph())
        out.append(item)
    return out


def _algorithm(algorithm) -> tuple[str, ox.CanonicalizationAlgorithm]:
    """Accept "sha256"/"sha384" (RDFC-1.0 with that hash) or a CanonicalizationAlgorithm."""
    if isinstance(algorithm, str):
        key = algorithm.lower().replace("-", "")
        if key not in _ALGORITHMS:
            raise ValueError(f"RDFC-1.0 specifies SHA-256 or SHA-384, not {algorithm!r}")
        return key, _ALGORITHMS[key]
    if algorithm == ox.CanonicalizationAlgorithm.RDFC_1_0:
        return "sha256", algorithm
    if algorithm == ox.CanonicalizationAlgorithm.RDFC_1_0_SHA_384:
        return "sha384", algorithm
    raise ValueError(f"not an RDFC-1.0 algorithm: {algorithm!r}")


def _bnode_in_triple_term(quads: list[ox.Quad]) -> bool:
    """Does any quad hold a triple term that contains a blank node, at any depth?"""
    for q in quads:
        o = q.object
        if not isinstance(o, ox.Triple):
            continue
        stack = [o]
        while stack:
            t = stack.pop()
            for part in (t.subject, t.object):
                if isinstance(part, ox.BlankNode):
                    return True
                if isinstance(part, ox.Triple):
                    stack.append(part)
    return False


def check_complexity(quads: list[ox.Quad], *, max_cycle_rank: int = MAX_SYMMETRIC_CYCLE_RANK) -> None:
    """Raise :class:`CanonicalizationComplexityError` if ``quads`` hold a blank-node structure that canonicalisation would not
    finish: colour refinement (every blank node is coloured by its quads, neighbours by their colours, until stable), then
    the blank nodes still sharing a colour are linked by the quads that join two of them; a connected group of them with
    more than ``max_cycle_rank`` independent cycles (edges - nodes + 1) is the symmetric, densely tied structure the
    algorithm's permutation step explodes on. Paths, trees, plain cycles, any number of interchangeable leaf blank nodes
    and a hub with many identical blank children never count. Linear in the quads (times the refinement rounds).

    A heuristic: it rejects every clique of 8 or more blank nodes and every grid-like symmetric graph that was seen to
    hang, and accepts every dataset of the W3C suite; it does not prove that a dataset it accepts finishes quickly."""
    nodes: dict[str, int] = {}

    def collect(t, acc):
        if isinstance(t, ox.BlankNode):
            acc.append(nodes.setdefault(t.value, len(nodes)))
        elif isinstance(t, ox.Triple):
            collect(t.subject, acc)
            collect(t.object, acc)

    rows = []
    for q in quads:
        acc: list[int] = []
        collect(q.subject, acc)
        collect(q.object, acc)
        collect(q.graph_name, acc)
        if acc:
            rows.append((q, acc))
    if len(nodes) < 8:
        return  # a dozen blank nodes finish in milliseconds whatever their shape; the cheapest clique that hangs has 8
    color = [0] * len(nodes)

    def show(t, own: int | None) -> str:
        if isinstance(t, ox.BlankNode):
            i = nodes[t.value]
            return "@" if i == own else f"_{color[i]}"
        if isinstance(t, ox.Triple):
            return f"<<{show(t.subject, own)} {t.predicate} {show(t.object, own)}>>"
        return str(t)

    classes = 1
    for _ in range(64):
        sigs: list[list[str]] = [[] for _ in nodes]
        for q, acc in rows:
            for i in set(acc):
                sigs[i].append(f"{show(q.subject, i)} {q.predicate} {show(q.object, i)} {show(q.graph_name, i)}")
        palette: dict[tuple, int] = {}
        new = [palette.setdefault((color[i], tuple(sorted(sigs[i]))), len(palette)) for i in range(len(nodes))]
        color = new
        if len(palette) == classes:
            break
        classes = len(palette)
    size: dict[int, int] = {}
    for c in color:
        size[c] = size.get(c, 0) + 1
    parent = list(range(len(nodes)))

    def find(x: int) -> int:
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    edges: set[tuple[int, int]] = set()
    for _, acc in rows:
        tied = sorted({i for i in acc if size[color[i]] > 1})
        for k, a in enumerate(tied):
            for b in tied[k + 1:]:
                edges.add((a, b))
                parent[find(a)] = find(b)
    count_nodes: dict[int, set[int]] = {}
    count_edges: dict[int, int] = {}
    for a, b in edges:
        r = find(a)
        count_nodes.setdefault(r, set()).update((a, b))
        count_edges[r] = count_edges.get(r, 0) + 1
    for r, e in count_edges.items():
        rank = e - len(count_nodes[r]) + 1
        if rank > max_cycle_rank:
            raise CanonicalizationComplexityError(
                f"canonicalisation refused: {len(count_nodes[r])} indistinguishable blank nodes are tied together by {e} "
                f"statements (cycle rank {rank} > {max_cycle_rank}); RDFC-1.0 takes exponential time on such a structure"
            )


def _canonicalize(quads: list[ox.Quad], algorithm) -> list[ox.Quad]:
    _, alg = _algorithm(algorithm)
    check_complexity(quads)
    ds = ox.Dataset(quads)  # a copy: the caller's store or dataset is never relabelled
    ds.canonicalize(alg)
    return list(ds)


def isomorphic(a, b, *, basic: bool = False) -> bool:
    """True if the two datasets (``Store``, ``Dataset`` or iterables of quads) are isomorphic: equal after
    RDFC-1.0 canonicalisation, so graph names count and blank-node graph names are handled by the
    algorithm. ``basic=True`` applies the basic encoding first (then triple terms are compared as their
    PropositionForm structure, which is also isomorphism-preserving)."""
    qa, qb = _quads(a), _quads(b)
    # pyoxigraph's native canonicalisation is not deterministic when blank nodes sit inside triple terms (it labelled the
    # blank-node cycle `_:b0 <p> <<( _:b1 <p> _:b2 )>> . _:b1 <p> <<( _:b2 <p> _:b0 )>> . _:b2 <p> <<( _:b0 <p> _:b1 )>>` with
    # two different labellings in 30 runs, so a graph was not isomorphic to itself about 40 percent of the time; see
    # docs/working/interop-and-rdfc.md). Such data goes through the basic encoding, whose RDFC-1.0 input has no triple term.
    basic = basic or _bnode_in_triple_term(qa) or _bnode_in_triple_term(qb)
    if basic:
        qa, qb = to_basic(qa), to_basic(qb)
    if len(set(qa)) != len(set(qb)):
        return False
    return set(_canonicalize(qa, "sha256")) == set(_canonicalize(qb, "sha256"))


def canonical_quads(dataset, *, algorithm="sha256", basic: bool = True) -> list[ox.Quad]:
    """The canonical quads, sorted by their N-Quads line. With ``basic=True`` (default) the basic encoding
    is applied first, so no triple term appears in the result. With ``basic=False`` the encoding is still applied when a
    triple term contains a blank node (the native labelling of that case is not deterministic)."""
    qs = _quads(dataset)
    basic = basic or _bnode_in_triple_term(qs)  # see isomorphic(): the native labelling of such data is not stable
    if basic:
        qs = to_basic(qs)
    return sorted(_canonicalize(qs, algorithm), key=_line)


def _line(q: ox.Quad) -> str:
    return ox.serialize([q], format=ox.RdfFormat.N_QUADS).decode()


def canonical_nquads(dataset, *, algorithm="sha256", basic: bool = True) -> str:
    """Canonical N-Quads text: one line per quad, sorted, as RDFC-1.0 section 4.4.3 step 7 specifies."""
    return "".join(sorted(_line(q) for q in canonical_quads(dataset, algorithm=algorithm, basic=basic)))


def canonical_hash(dataset, *, algorithm="sha256", basic: bool = True) -> str:
    """Hex digest (SHA-256 by default, or SHA-384) of the canonical N-Quads text."""
    key, _ = _algorithm(algorithm)
    return _HASHES[key](canonical_nquads(dataset, algorithm=algorithm, basic=basic).encode("utf-8")).hexdigest()
