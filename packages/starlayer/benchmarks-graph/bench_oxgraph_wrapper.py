"""
benchmarks-graph/bench_oxgraph_wrapper.py

100k-triple comparison of the old ``StarLayerGraph`` (rdflib store), the Oxigraph wrapper ``StarLayerGraph`` and a bare
``pyoxigraph.Store``, on load (N-Triples text and one-by-one ``add``), query (a join, an aggregate, a point lookup) and iteration.
Median of REPEATS runs, seconds. Run:

    PYTHONPATH=packages/starlayer python3 packages/starlayer/benchmarks-graph/bench_oxgraph_wrapper.py [--triples 100000]
"""

from __future__ import annotations

import argparse
import statistics
import time

import pyoxigraph as ox

EX = "http://example.org/"
REPEATS = 3
Q_JOIN = f"SELECT (COUNT(*) AS ?n) WHERE {{ ?a <{EX}knows> ?b . ?b <{EX}knows> ?c }}"
Q_AGG = "SELECT ?t (COUNT(?s) AS ?n) WHERE { ?s a ?t } GROUP BY ?t"
Q_POINT = f"SELECT ?o WHERE {{ <{EX}n17> <{EX}name> ?o }}"


def make_ntriples(n: int) -> str:
    """~n triples: each person has a type, a name, an age and two knows edges."""
    lines = []
    people = max(1, n // 5)
    for i in range(people):
        s = f"<{EX}n{i}>"
        lines.append(f"{s} <http://www.w3.org/1999/02/22-rdf-syntax-ns#type> <{EX}T{i % 7}> .")
        lines.append(f'{s} <{EX}name> "person {i}" .')
        lines.append(f'{s} <{EX}age> "{i % 90}"^^<http://www.w3.org/2001/XMLSchema#integer> .')
        lines.append(f"{s} <{EX}knows> <{EX}n{(i * 7 + 1) % people}> .")
        lines.append(f"{s} <{EX}knows> <{EX}n{(i * 13 + 5) % people}> .")
    return "\n".join(lines) + "\n"


def timed(fn):
    t = time.perf_counter()
    out = fn()
    return time.perf_counter() - t, out


def median(fn, repeats=REPEATS):
    return statistics.median(timed(fn)[0] for _ in range(repeats))


class Old:
    name = "StarLayerGraph"

    def __init__(self):
        from starlayer.graph.graph.starlayer_graph import StarLayerGraph

        self.cls = StarLayerGraph

    def load(self, text):
        g = self.cls()
        g.parse(data=text, format="nt")
        return g

    def add_loop(self, triples):
        from rdflib import Literal, URIRef

        g = self.cls()
        for s, p, o in triples:
            g.add((URIRef(s), URIRef(p), URIRef(o) if o.startswith("http") else Literal(o)))
        return g

    def query(self, g, q):
        return len(list(g.query(q)))

    def iterate(self, g):
        return sum(1 for _ in g)

    def lookup(self, g, n):
        from rdflib import URIRef

        return sum(1 for i in range(n) for _ in g.triples((URIRef(f"{EX}n{i}"), None, None)))


class Wrapper:
    name = "StarLayerGraph"

    def load(self, text):
        from starlayer.graph.oxgraph import StarLayerGraph

        g = StarLayerGraph()
        g.parse(data=text, format="nt")
        return g

    def add_loop(self, triples):
        from starlayer.graph.oxgraph import StarLayerGraph

        g = StarLayerGraph()
        for s, p, o in triples:
            g.add((ox.NamedNode(s), ox.NamedNode(p), ox.NamedNode(o) if o.startswith("http") else ox.Literal(o)))
        return g

    def query(self, g, q):
        return len(list(g.query(q)))

    def iterate(self, g):
        return sum(1 for _ in g)

    def lookup(self, g, n):
        return sum(1 for i in range(n) for _ in g.triples((ox.NamedNode(f"{EX}n{i}"), None, None)))


class Bare:
    name = "pyoxigraph.Store"

    def load(self, text):
        s = ox.Store()
        s.load(text.encode(), format=ox.RdfFormat.N_TRIPLES)
        return s

    def add_loop(self, triples):
        s = ox.Store()
        for a, p, o in triples:
            s.add(ox.Quad(ox.NamedNode(a), ox.NamedNode(p), ox.NamedNode(o) if o.startswith("http") else ox.Literal(o)))
        return s

    def query(self, s, q):
        return len(list(s.query(q)))

    def iterate(self, s):
        return sum(1 for _ in s)

    def lookup(self, s, n):
        return sum(1 for i in range(n) for _ in s.quads_for_pattern(ox.NamedNode(f"{EX}n{i}"), None, None, None))


def bench(impl, text: str, n_lines: int, loop_triples: list) -> dict[str, float]:
    r: dict[str, float] = {}
    r[f"load nt ({n_lines})"] = median(lambda: impl.load(text), 1 if impl.name == "StarLayerGraph" else REPEATS)
    r[f"add x{len(loop_triples)}"] = median(lambda: impl.add_loop(loop_triples))
    g = impl.load(text)
    r["query join (count)"] = median(lambda: impl.query(g, Q_JOIN))
    r["query group-by"] = median(lambda: impl.query(g, Q_AGG))
    r["query point x1"] = median(lambda: impl.query(g, Q_POINT))
    r["iterate all"] = median(lambda: impl.iterate(g))
    r["1000 pattern lookups"] = median(lambda: impl.lookup(g, 1000))
    return r


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--triples", type=int, default=100_000)
    ap.add_argument("--add-loop", type=int, default=20_000, help="triples written one by one")
    args = ap.parse_args()
    text = make_ntriples(args.triples)
    n_lines = text.count("\n")
    loop_triples = [(f"{EX}s{i}", f"{EX}p", f"{EX}o{i}" if i % 2 else f"v{i}") for i in range(args.add_loop)]
    impls = [Old(), Wrapper(), Bare()]
    rows = {impl.name: bench(impl, text, n_lines, loop_triples) for impl in impls}
    names = [i.name for i in impls]
    ops = list(rows[names[0]])
    print(f"{'operation (seconds, median)':32}" + "".join(f"{n:>20}" for n in names) + f"{'old/wrapper':>14}")
    for op in ops:
        vals = [rows[n][op] for n in names]
        print(f"{op:32}" + "".join(f"{v:20.4f}" for v in vals) + f"{vals[0] / vals[1]:14.1f}")


if __name__ == "__main__":
    main()
