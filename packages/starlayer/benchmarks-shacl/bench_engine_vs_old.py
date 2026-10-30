"""Benchmark the native SHACL 1.2 engine (starlayer.shacl_engine) against the pyshacl-backed validator.

Configurations: (a) old validator on StarLayerGraph, (b) new engine on StarLayerGraph, (c) new engine on OxigraphGraph.
Every measurement runs in its own subprocess so peak RSS (``resource.getrusage``) is per configuration. Best of 3 for
data up to ``--repeat-max`` triples, one run above that. Sizes stop growing once a run exceeds ``--stop-after`` seconds.

    PYTHONPATH=packages/starlayer python3 benchmarks-shacl/bench_engine_vs_old.py --sizes 1000,10000,50000,200000
    PYTHONPATH=packages/starlayer python3 benchmarks-shacl/bench_engine_vs_old.py --profile 10000

The adapter benchmark data (bench_adapter.py) is triple-term encode/decode only and has no shapes, so the data and shapes
here are generated: a people/org/address graph (~14 triples per person, ~3% planted violations) and a shapes graph with
cardinality+datatype+pattern, sh:class over a subclass hierarchy, sh:node/sh:and, sh:sparql, sh:uniqueValuesFor and
sh:qualifiedValueShape.
"""

from __future__ import annotations

import argparse
import cProfile
import json
import pstats
import resource
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

CONFIGS = ("old-slg", "new-slg", "new-ox")
PER_PERSON = 14

SHAPES_TTL = """
@prefix ex: <http://example.org/> . @prefix sh: <http://www.w3.org/ns/shacl#> . @prefix xsd: <http://www.w3.org/2001/XMLSchema#> .
ex:PersonShape a sh:NodeShape ; sh:targetClass ex:Person ;
  sh:and ( ex:ContactShape ex:AddressedShape ) ;
  sh:property [ sh:path ex:name ; sh:minCount 1 ; sh:maxCount 1 ; sh:datatype xsd:string ] ;
  sh:property [ sh:path ex:age ; sh:maxCount 1 ; sh:datatype xsd:integer ; sh:minInclusive 0 ; sh:maxInclusive 150 ] ;
  sh:property [ sh:path ex:worksFor ; sh:class ex:Org ] ;
  sh:property [ sh:path ex:skill ; sh:qualifiedValueShape [ sh:class ex:Cert ] ; sh:qualifiedMinCount 1 ] ;
  sh:sparql [ a sh:SPARQLConstraint ; sh:message "age and id must be consistent" ;
    sh:select "SELECT $this ?value WHERE { $this <http://example.org/age> ?value . FILTER(?value > 120) }" ] .
ex:ContactShape a sh:NodeShape ;
  sh:property [ sh:path ex:email ; sh:minCount 1 ; sh:datatype xsd:string ; sh:pattern "^[a-z0-9]+@example\\\\.org$" ] .
ex:AddressedShape a sh:NodeShape ; sh:property [ sh:path ex:address ; sh:minCount 1 ; sh:maxCount 1 ; sh:node ex:AddressShape ] .
ex:AddressShape a sh:NodeShape ;
  sh:property [ sh:path ex:city ; sh:minCount 1 ; sh:datatype xsd:string ] ;
  sh:property [ sh:path ex:zip ; sh:pattern "^[0-9]{5}$" ] .
ex:EmployeeShape a sh:NodeShape ; sh:targetClass ex:Employee ; sh:uniqueValuesFor ex:id .
"""


def make_data(triples: int):
    """~PER_PERSON triples per person; every 33rd person gets a violation of some kind."""
    from rdflib import RDF, RDFS, Literal, Namespace
    from rdflib.namespace import XSD
    from starlayer import StarLayerGraph

    ex = Namespace("http://example.org/")
    g = StarLayerGraph()
    for sub, sup in ((ex.Employee, ex.Person), (ex.Manager, ex.Employee), (ex.Company, ex.Org), (ex.Startup, ex.Company)):
        g.add((sub, RDFS.subClassOf, sup))
    for i in range(10):
        g.add((ex[f"org{i}"], RDF.type, ex.Startup if i % 2 else ex.Company))
    for j in range(5):
        g.add((ex[f"cert{j}"], RDF.type, ex.Cert))
    for i in range(max(1, triples // PER_PERSON)):
        p, a = ex[f"p{i}"], ex[f"addr{i}"]
        bad = i % 33 == 0
        g.add((p, RDF.type, ex.Manager if i % 10 == 0 else ex.Employee))
        if not (bad and i % 4 == 0):
            g.add((p, ex.name, Literal(f"Person {i}")))
        g.add((p, ex.email, Literal(f"u{i}@example.org" if not (bad and i % 3 == 0) else "bad email")))
        g.add((p, ex.age, Literal(30 + i % 40 if not (bad and i % 2 == 0) else 200, datatype=XSD.integer)))
        g.add((p, ex.id, Literal(f"id{i}" if not (bad and i % 5 == 0 and i > 0) else "id1")))
        g.add((p, ex.address, a))
        g.add((a, ex.city, Literal(f"City {i % 50}")))
        g.add((a, ex.zip, Literal(f"{10000 + i % 90000:05d}" if not (bad and i % 7 == 0) else "abc")))
        g.add((p, ex.worksFor, ex[f"org{i % 10}"] if not (bad and i % 6 == 0) else ex.p0))
        for k in range(3):
            g.add((p, ex.skill, ex[f"cert{(i + k) % 5}"] if not (bad and k == 0 and i % 8 == 0) else ex[f"plain{i}_{k}"]))
        g.add((p, ex.knows, ex[f"p{(i * 7 + 1) % max(1, triples // PER_PERSON)}"]))
    return g


def make_shapes(unique: bool = True):
    """The full shapes set; ``unique=False`` drops the sh:uniqueValuesFor shape (the new engine compares every focus node
    with every other, so it is quadratic and dominates everything else from ~10k triples up)."""
    from starlayer import StarLayerGraph

    s = StarLayerGraph()
    ttl = SHAPES_TTL if unique else SHAPES_TTL.replace("sh:uniqueValuesFor ex:id", "sh:closed false")
    s.parse(data=ttl, format="turtle")
    return s


def count_results_old(res) -> int:
    from rdflib import RDF, Namespace

    sh = Namespace("http://www.w3.org/ns/shacl#")
    return sum(1 for _ in res.report_graph.subjects(RDF.type, sh.ValidationResult))


def _ox_graph_class():
    """OxigraphGraph as it ships has ``query()`` but not the ``sparql_query()`` hook sparql_support.run_query looks for, so
    sh:sparql crashes on it (TypeError: unexpected keyword 'initBindings'). This subclass adds the missing hook - the fast
    path the design intends - so the Oxigraph column can run the full shapes set."""
    from starlayer.shacl_engine.oxigraph_view import OxigraphGraph
    from starlayer.shacl_engine.sparql_support import Solutions

    class BenchOxigraph(OxigraphGraph):
        def sparql_query(self, text, init_bindings=None):
            res = self.query(text, init_bindings)
            if isinstance(res, bool):
                return Solutions(boolean=res)
            names = tuple(sorted({k for row in res for k in row}))
            return Solutions(variables=names, rows=tuple(res))

    return BenchOxigraph


def _runner(config: str, data, shapes):
    """Return (callable running one validation, setup_seconds). The callable returns the result count."""
    t0 = time.perf_counter()
    if config == "old-slg":
        from starlayer.shacl.validator import validate

        return (lambda: count_results_old(validate(data, shapes, meta_shacl=False))), 0.0
    from starlayer.shacl_engine.api import validate

    if config == "new-slg":
        return (lambda: len(validate(data, shapes).results)), 0.0
    ox_data = _ox_graph_class().from_graph(data)
    return (lambda: len(validate(ox_data, shapes).results)), time.perf_counter() - t0


def child(config: str, triples: int, reps: int, unique: bool) -> None:
    data, shapes = make_data(triples), make_shapes(unique)
    n_triples = len(data)
    rss0 = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    fn, setup = _runner(config, data, shapes)
    rss_loaded = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    times, count = [], None
    for _ in range(reps):
        t = time.perf_counter()
        count = fn()
        times.append(time.perf_counter() - t)
    rss = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    div = 1 if sys.platform == "darwin" else 1024  # macOS reports bytes, Linux KiB (rss / 1e6 or / 1e3 gives MB)
    print(json.dumps({"triples": n_triples, "best": min(times), "count": count, "setup": setup,
                      "rss_mb": rss / (1e6 if div == 1 else 1e3),
                      "rss_delta_mb": (rss - rss0) / (1e6 if div == 1 else 1e3), "rss_loaded_mb": rss_loaded / (1e6 if div == 1 else 1e3)}))


def run_child(config: str, triples: int, reps: int, timeout: float, unique: bool) -> dict | None:
    cmd = [sys.executable, __file__, "--child", config, "--triples", str(triples), "--reps", str(reps)] + ([] if unique else ["--no-unique"])
    try:
        out = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, check=True)
    except subprocess.TimeoutExpired:
        return None
    except subprocess.CalledProcessError as e:
        print(e.stderr[-2000:], file=sys.stderr)
        return None
    return json.loads(out.stdout.strip().splitlines()[-1])


def profile(triples: int, top: int, unique: bool) -> None:
    for config in ("new-slg", "new-ox"):
        data, shapes = make_data(triples), make_shapes(unique)
        fn, _ = _runner(config, data, shapes)
        pr = cProfile.Profile()
        pr.enable()
        fn()
        pr.disable()
        st = pstats.Stats(pr)
        print(f"\n=== profile {config}, {len(data)} triples: total {st.total_tt:.2f}s (profiler-inflated) ===")
        st.sort_stats("cumulative").print_stats(top)
        st.sort_stats("tottime").print_stats(top)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--sizes", default="1000,10000,50000,200000")
    ap.add_argument("--repeat-max", type=int, default=10000)
    ap.add_argument("--stop-after", type=float, default=300.0)
    ap.add_argument("--profile", type=int, metavar="TRIPLES")
    ap.add_argument("--top", type=int, default=30)
    ap.add_argument("--no-unique", action="store_true", help="drop the sh:uniqueValuesFor shape")
    ap.add_argument("--child", choices=CONFIGS)
    ap.add_argument("--triples", type=int)
    ap.add_argument("--reps", type=int, default=1)
    a = ap.parse_args()
    if a.child:
        child(a.child, a.triples, a.reps, not a.no_unique)
        return
    if a.profile:
        profile(a.profile, a.top, not a.no_unique)
        return
    import platform

    print('shapes:', 'no sh:uniqueValuesFor' if a.no_unique else 'full set')

    import pyoxigraph
    import rdflib

    print(f"python {platform.python_version()} rdflib {rdflib.__version__} pyoxigraph {pyoxigraph.__version__} {platform.platform()}")
    print("| triples | config | best s | setup s | results | peak RSS MB | RSS growth MB | note |")
    print("|---|---|---|---|---|---|---|---|")
    stopped = set()
    for size in (int(s) for s in a.sizes.split(",")):
        counts = {}
        for config in CONFIGS:
            if config in stopped:
                continue
            reps = 3 if size <= a.repeat_max else 1
            t = time.perf_counter()
            r = run_child(config, size, reps, timeout=a.stop_after * reps * 2, unique=not a.no_unique)
            if r is None:
                print(f"| {size} | {config} | - | - | - | - | - | failed/timeout |")
                stopped.add(config)
                continue
            counts[config] = r["count"]
            if r["best"] > a.stop_after:
                stopped.add(config)
            print(f"| {r['triples']} | {config} | {r['best']:.2f} | {r['setup']:.2f} | {r['count']} | {r['rss_mb']:.0f} | {r['rss_delta_mb']:.0f} | wall incl. data gen {time.perf_counter() - t:.0f}s |", flush=True)
        if len(set(counts.values())) > 1:
            print(f"| {size} | DISAGREEMENT | | | {counts} | | | |", flush=True)


if __name__ == "__main__":
    main()
