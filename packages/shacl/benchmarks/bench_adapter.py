from __future__ import annotations

import argparse
import sys
import time
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from rdflib import Namespace

from starshacl import TripleTermAdapter
from starshacl.adapters import TripleTermGraph, TripleTermValue


EX = Namespace("http://example.org/")


@dataclass(frozen=True)
class BenchResult:
    triples: int
    nested_depth: int
    encode_ms: float
    decode_ms: float
    support_triples: int


def _make_term(index: int, depth: int):
    base = TripleTermValue(EX[f"s{index}"], EX.p, EX[f"o{index}"])
    term = base
    for _ in range(depth - 1):
        term = TripleTermValue(EX[f"n{index}"], EX.p, term)
    return term


def _build_graph(triples: int, nested_depth: int) -> TripleTermGraph:
    g = TripleTermGraph()
    for i in range(triples):
        g.add((EX[f"root{i}"], EX.asserts, _make_term(i, nested_depth)))
    return g


def run_benchmark(triples: int, nested_depth: int) -> BenchResult:
    graph = _build_graph(triples, nested_depth)
    adapter = TripleTermAdapter()

    t0 = time.perf_counter()
    encoded = adapter.encode_graph(graph)
    t1 = time.perf_counter()

    _ = adapter.decode_graph(encoded)
    t2 = time.perf_counter()

    return BenchResult(
        triples=triples,
        nested_depth=nested_depth,
        encode_ms=(t1 - t0) * 1000.0,
        decode_ms=(t2 - t1) * 1000.0,
        support_triples=adapter.support_triple_count(),
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Benchmark starShacl triple-term adapter encode/decode paths.")
    parser.add_argument("--triples", type=int, default=1000)
    parser.add_argument("--nested-depth", type=int, default=1)
    args = parser.parse_args()

    result = run_benchmark(triples=args.triples, nested_depth=args.nested_depth)

    print("starShacl adapter benchmark")
    print(f"triples: {result.triples}")
    print(f"nested_depth: {result.nested_depth}")
    print(f"encode_ms: {result.encode_ms:.3f}")
    print(f"decode_ms: {result.decode_ms:.3f}")
    print(f"support_triples: {result.support_triples}")


if __name__ == "__main__":
    main()
