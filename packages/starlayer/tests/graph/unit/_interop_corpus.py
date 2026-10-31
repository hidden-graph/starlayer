"""Random RDF 1.2 dataset generator and helpers shared by the interop / native-RDFC tests (seeded, no Hypothesis)."""

from __future__ import annotations

import itertools
import random

import pyoxigraph as ox

NS = "http://e/"


def iri(s: str) -> ox.NamedNode:
    return ox.NamedNode(NS + s)


def gen_dataset(rng: random.Random, *, named_graphs: bool = True, triple_terms: bool = True,
                bnode_graphs: bool = True, directions: bool = True, max_bnodes: int = 4) -> list[ox.Quad]:
    nb = rng.randint(0, max_bnodes)
    bnodes = [ox.BlankNode(f"b{i}") for i in range(nb)]
    iris = [iri(c) for c in "abc"]
    preds = [iri(c) for c in "pq"]
    lits = [ox.Literal("x"), ox.Literal("y", language="en"), ox.Literal("1", datatype=ox.NamedNode("http://www.w3.org/2001/XMLSchema#integer"))]
    if directions:
        lits.append(ox.Literal("z", language="ar", direction=ox.BaseDirection.RTL))
    graphs = [ox.DefaultGraph()]
    if named_graphs:
        graphs += [iri("g1")] + (bnodes[:1] if bnode_graphs else [])

    def subj():
        return rng.choice(iris + bnodes)

    def tt(depth=0):
        o = rng.choice(iris + bnodes + lits)
        if depth < 2 and rng.random() < 0.3:
            o = tt(depth + 1)
        return ox.Triple(subj(), rng.choice(preds), o)

    def obj():
        r = rng.random()
        if triple_terms and r < 0.25:
            return tt()
        return rng.choice(iris + bnodes + lits)

    return list({ox.Quad(subj(), rng.choice(preds), obj(), rng.choice(graphs)) for _ in range(rng.randint(1, 7))})


def _map_term(t, m):
    if isinstance(t, ox.BlankNode):
        return m.get(t.value, t)
    if isinstance(t, ox.Triple):
        return ox.Triple(_map_term(t.subject, m), t.predicate, _map_term(t.object, m))
    return t


def bnode_labels(quads) -> set[str]:
    out: set[str] = set()

    def walk(t):
        if isinstance(t, ox.BlankNode):
            out.add(t.value)
        elif isinstance(t, ox.Triple):
            walk(t.subject)
            walk(t.object)

    for q in quads:
        for t in (q.subject, q.object, q.graph_name):
            walk(t)
    return out


def relabel(quads, rng: random.Random, shuffle=True) -> list[ox.Quad]:
    labels = sorted(bnode_labels(quads))
    new = [f"n{i}x{rng.randint(0, 99)}" for i in range(len(labels))]
    m = dict(zip(labels, (ox.BlankNode(n) for n in new), strict=True))
    out = [ox.Quad(_map_term(q.subject, m), q.predicate, _map_term(q.object, m), _map_term(q.graph_name, m)) for q in quads]
    if shuffle:
        rng.shuffle(out)
    return out


def brute_isomorphic(a, b) -> bool:
    """Ground truth: try every bijection of blank-node labels (use only for few blank nodes)."""
    la, lb = sorted(bnode_labels(a)), sorted(bnode_labels(b))
    if len(la) != len(lb) or len(set(a)) != len(set(b)):
        return False
    sb = set(b)
    for perm in itertools.permutations(lb):
        m = {x: ox.BlankNode("m" + y) for x, y in zip(la, perm, strict=True)}
        mb = {x: ox.BlankNode("m" + x) for x in lb}
        sa = {ox.Quad(_map_term(q.subject, m), q.predicate, _map_term(q.object, m), _map_term(q.graph_name, m)) for q in a}
        sbm = {ox.Quad(_map_term(q.subject, mb), q.predicate, _map_term(q.object, mb), _map_term(q.graph_name, mb)) for q in sb}
        if sa == sbm:
            return True
    return False


def mutate(quads, rng: random.Random) -> list[ox.Quad]:
    """A near miss: one quad's predicate swapped, or one quad dropped, or an object bnode rewired."""
    qs = list(quads)
    i = rng.randrange(len(qs))
    q = qs[i]
    r = rng.random()
    if r < 0.4:
        qs[i] = ox.Quad(q.subject, iri("r"), q.object, q.graph_name)
    elif r < 0.6 and len(qs) > 1:
        del qs[i]
    else:
        bs = sorted(bnode_labels(qs))
        if bs and not isinstance(q.object, (ox.Triple,)):
            qs[i] = ox.Quad(q.subject, q.predicate, ox.BlankNode(rng.choice(bs)), q.graph_name)
        else:
            qs[i] = ox.Quad(q.subject, iri("r"), q.object, q.graph_name)
    return list(set(qs))


def symmetric_pair(rng: random.Random):
    """Two datasets with equal degree sequences: one 4-cycle of blank nodes against two 2-cycles
    (isomorphic only if the shapes match), optionally wrapped in triple terms. Hard cases for colour refinement."""
    p = iri("p")
    def cyc(sizes, wrap):
        qs, k = [], 0
        for n in sizes:
            ids = [ox.BlankNode(f"c{k + j}") for j in range(n)]
            k += n
            for j in range(n):
                s, o = ids[j], ids[(j + 1) % n]
                qs.append(ox.Quad(s, p, ox.Triple(iri("a"), p, o) if wrap else o, ox.DefaultGraph()))
        return qs
    wrap = rng.random() < 0.5
    return cyc([4], wrap), cyc([2, 2], wrap), cyc([4], wrap)
